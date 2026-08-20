#!/usr/bin/env python3
"""d=640 fixed-voice Hinglish student: architecture + structured init from the 265M teacher.

The student is the XTTS GPT backbone narrowed d=1024 -> 640, with the speaker pathway
(conditioning_encoder + perceiver) DELETED (we bake the 4 fixed voices' conditioning), plus a
learned 640 -> 1024 adapter on the GPT latents so the FROZEN HiFi-GAN (decoder_input_dim=1024)
still receives 1024-d input.

Init is structured, never random (Minitron practice):
  - residual stream (the d axis): keep the top-640 channels from channel_importance.pt (keep_idx)
  - attention: keep 10 whole heads/layer (head_dim 64 preserved) by value-proj x output-proj norm
  - FFN: keep 2560 neurons/layer (4*640) by  ||c_fc col|| * ||c_proj row||
  - adapter: scatter-to-kept-positions, so adapter(student_latent) ~= teacher_latent at step 0

Shapes (HF Conv1D stores weight as (in_features, out_features), x @ W):
  c_attn (d, 3d)   c_proj_attn (d, d)   mlp.c_fc (d, 4d)   mlp.c_proj (4d, d)
"""
from __future__ import annotations
import torch
import torch.nn as nn

HEAD_DIM = 64          # preserved across all widths: heads = d / 64 (1024->16, 768->12, 640->10)
GPT_PREFIX = "xtts.gpt."


# ---------------------------------------------------------------- selection
def head_importance(c_attn_w: torch.Tensor, c_proj_w: torch.Tensor) -> torch.Tensor:
    """Per-head importance = ||value-proj of head||_F * ||output-proj of head||_F.
    c_attn_w: (d, 3d) = [q|k|v] each (d, d).  c_proj_w: (d, d) in=heads*head_dim, out=residual.
    teacher_d + teacher_heads inferred from c_attn_w (works for any teacher width)."""
    d = c_attn_w.shape[0]
    teacher_heads = d // HEAD_DIM
    v_block = c_attn_w[:, 2 * d:]                       # (d, d) value projection (out = head channels)
    imp = torch.zeros(teacher_heads)
    for h in range(teacher_heads):
        sl = slice(h * HEAD_DIM, (h + 1) * HEAD_DIM)
        v_norm = v_block[:, sl].norm()                 # head h's value output channels
        o_norm = c_proj_w[sl, :].norm()                # head h's contribution into the residual
        imp[h] = v_norm * o_norm
    return imp


def ffn_importance(c_fc_w: torch.Tensor, c_proj_w: torch.Tensor) -> torch.Tensor:
    """Per-neuron importance = ||c_fc column||_2 * ||c_proj row||_2.
    c_fc_w: (d, 4d) col j = neuron j input weights.  c_proj_w: (4d, d) row j = neuron j output weights."""
    return c_fc_w.norm(dim=0) * c_proj_w.norm(dim=1)   # (4d,)


def head_channels(head_keep: torch.Tensor) -> torch.Tensor:
    """Expand kept head indices -> the (heads*head_dim) channel indices they occupy."""
    return torch.cat([torch.arange(h * HEAD_DIM, (h + 1) * HEAD_DIM) for h in head_keep.tolist()])


def qkv_columns(head_keep: torch.Tensor, teacher_d: int) -> torch.Tensor:
    """Columns to keep in the (3d) c_attn output: kept-head channels within each of q, k, v blocks."""
    hc = head_channels(head_keep)
    return torch.cat([hc, hc + teacher_d, hc + 2 * teacher_d])


# ---------------------------------------------------------------- init
@torch.no_grad()
def slice_teacher_into_student(student_gpt: nn.Module, tsd: dict, keep_idx: torch.Tensor,
                               student_ffn: int, verbose: bool = True) -> dict:
    """Fill student_gpt (already built at d=640) from teacher GPT state-dict tsd (keys w/o GPT_PREFIX).
    Returns a per-layer record of the head/neuron selections (needed later for analysis)."""
    keep = keep_idx.long()
    ssd = student_gpt.state_dict()
    d_s = keep.numel()
    record = {"keep_idx": keep, "heads": {}, "ffn": {}}

    def put(name, tensor):
        assert ssd[name].shape == tensor.shape, f"{name}: student {tuple(ssd[name].shape)} != sliced {tuple(tensor.shape)}"
        ssd[name].copy_(tensor)

    # --- token / position embeddings + final norm + heads (slice the d axis only) ---
    put("text_embedding.weight", tsd["text_embedding.weight"][:, keep])
    put("mel_embedding.weight", tsd["mel_embedding.weight"][:, keep])
    put("text_pos_embedding.emb.weight", tsd["text_pos_embedding.emb.weight"][:, keep])
    put("mel_pos_embedding.emb.weight", tsd["mel_pos_embedding.emb.weight"][:, keep])
    put("final_norm.weight", tsd["final_norm.weight"][keep])
    put("final_norm.bias", tsd["final_norm.bias"][keep])
    put("text_head.weight", tsd["text_head.weight"][:, keep]); put("text_head.bias", tsd["text_head.bias"])
    put("mel_head.weight", tsd["mel_head.weight"][:, keep]); put("mel_head.bias", tsd["mel_head.bias"])
    put("gpt.ln_f.weight", tsd["gpt.ln_f.weight"][keep]); put("gpt.ln_f.bias", tsd["gpt.ln_f.bias"][keep])

    n_layers = sum(1 for k in tsd if k.startswith("gpt.h.") and k.endswith(".ln_1.weight"))
    ffn_n = student_ffn
    for i in range(n_layers):
        p = f"gpt.h.{i}."
        # layer norms
        put(p + "ln_1.weight", tsd[p + "ln_1.weight"][keep]); put(p + "ln_1.bias", tsd[p + "ln_1.bias"][keep])
        put(p + "ln_2.weight", tsd[p + "ln_2.weight"][keep]); put(p + "ln_2.bias", tsd[p + "ln_2.bias"][keep])

        # attention: pick top-10 heads, copy whole head blocks
        c_attn_w = tsd[p + "attn.c_attn.weight"]; c_attn_b = tsd[p + "attn.c_attn.bias"]
        c_proj_w = tsd[p + "attn.c_proj.weight"]; c_proj_b = tsd[p + "attn.c_proj.bias"]
        n_heads_s = student_gpt.gpt.h[i].attn.num_heads if hasattr(student_gpt.gpt.h[i].attn, "num_heads") else d_s // HEAD_DIM
        h_imp = head_importance(c_attn_w, c_proj_w)
        head_keep = torch.sort(torch.topk(h_imp, n_heads_s).indices).values
        record["heads"][i] = head_keep
        teacher_d = c_attn_w.shape[0]
        qkv_cols = qkv_columns(head_keep, teacher_d); hc = head_channels(head_keep)
        put(p + "attn.c_attn.weight", c_attn_w[keep][:, qkv_cols])      # (d_s, 3*d_s)
        put(p + "attn.c_attn.bias", c_attn_b[qkv_cols])                 # (3*d_s,)
        put(p + "attn.c_proj.weight", c_proj_w[hc][:, keep])            # (d_s, d_s)
        put(p + "attn.c_proj.bias", c_proj_b[keep])                     # (d_s,)

        # FFN: pick top-2560 neurons
        c_fc_w = tsd[p + "mlp.c_fc.weight"]; c_fc_b = tsd[p + "mlp.c_fc.bias"]
        m_proj_w = tsd[p + "mlp.c_proj.weight"]; m_proj_b = tsd[p + "mlp.c_proj.bias"]
        f_imp = ffn_importance(c_fc_w, m_proj_w)
        ffn_keep = torch.sort(torch.topk(f_imp, ffn_n).indices).values
        record["ffn"][i] = ffn_keep
        put(p + "mlp.c_fc.weight", c_fc_w[keep][:, ffn_keep])           # (d_s, ffn_n)
        put(p + "mlp.c_fc.bias", c_fc_b[ffn_keep])                      # (ffn_n,)
        put(p + "mlp.c_proj.weight", m_proj_w[ffn_keep][:, keep])       # (ffn_n, d_s)
        put(p + "mlp.c_proj.bias", m_proj_b[keep])                      # (d_s,)

    student_gpt.load_state_dict(ssd)
    if verbose:
        print(f"[init] sliced {n_layers} layers into d={d_s} student ({d_s // HEAD_DIM} heads x {HEAD_DIM}, ffn={ffn_n})")
    return record


@torch.no_grad()
def init_adapter(adapter: nn.Linear, keep_idx: torch.Tensor):
    """Scatter init: adapter(x)[keep_idx[p]] = x[p], else 0.  Frozen vocoder ~ sees teacher latents at step 0."""
    adapter.weight.zero_(); adapter.bias.zero_()
    for p, c in enumerate(keep_idx.long().tolist()):
        adapter.weight[c, p] = 1.0


# ---------------------------------------------------------------- module
class Student640(nn.Module):
    """Trainable student = narrowed GPT (no speaker pathway) + 640->1024 latent adapter.
    The frozen HiFi-GAN + DVAE are held externally (teacher Xtts) at decode time."""
    def __init__(self, gpt: nn.Module, d_student: int = 640, d_vocoder: int = 1024):
        super().__init__()
        self.gpt = gpt
        self.adapter = nn.Linear(d_student, d_vocoder, bias=True)

    def vocoder_latents(self, gpt_latents640: torch.Tensor) -> torch.Tensor:
        return self.adapter(gpt_latents640)

    def n_params(self) -> int:
        return sum(p.numel() for p in self.parameters())


@torch.no_grad()
def _noop():  # marker
    pass


def forward_both(gpt: nn.Module, text_inputs, text_lengths, audio_codes, wav_lengths, cond_latents,
                 label_smoothing: float = 0.0):
    """One GPT forward (works for teacher d=1024 OR student d=640) returning BOTH:
        loss_mel (CE on GT codes), mel_logits (b, C, L), mel_latents (b, L, d), valid_mask (b, L).
    Faithful copy of GPT.forward but: conditioning is the BAKED cond_latents (b,32,d) (no speaker pathway),
    and the cond attn-mask is built from cond_latents (the stock forward needs cond_mels, which is None here).
    """
    import torch.nn.functional as F
    code_stride_len = gpt.code_stride_len
    max_text_len = text_lengths.max()
    code_lengths = torch.ceil(wav_lengths / code_stride_len).long() + 3
    max_mel_len = code_lengths.max()
    if max_mel_len > audio_codes.shape[-1]:
        audio_codes = F.pad(audio_codes, (0, max_mel_len - audio_codes.shape[-1]))

    text_inputs = F.pad(text_inputs[:, :max_text_len], (0, 1), value=gpt.stop_text_token)
    audio_codes = F.pad(audio_codes[:, :max_mel_len], (0, 1), value=gpt.stop_audio_token)
    audio_codes = gpt.set_mel_padding(audio_codes, code_lengths - 3)
    text_inputs, text_targets = gpt.set_inputs_and_targets(text_inputs, gpt.start_text_token, gpt.stop_text_token)
    audio_codes, mel_targets = gpt.set_inputs_and_targets(audio_codes, gpt.start_audio_token, gpt.stop_audio_token)

    b = text_inputs.shape[0]
    offset = cond_latents.shape[1]                       # 32 baked conditioning tokens
    attn_mask_cond = torch.ones(b, offset, dtype=torch.bool, device=text_inputs.device)
    attn_mask_text = torch.ones(text_inputs.shape[0], text_inputs.shape[1], dtype=torch.bool, device=text_inputs.device)
    attn_mask_mel = torch.ones(audio_codes.shape[0], audio_codes.shape[1], dtype=torch.bool, device=audio_codes.device)
    for idx, l in enumerate(text_lengths):
        attn_mask_text[idx, l + 1:] = 0
    for idx, l in enumerate(code_lengths):
        attn_mask_mel[idx, l + 1:] = 0

    text_emb = gpt.text_embedding(text_inputs) + gpt.text_pos_embedding(text_inputs)
    mel_emb = gpt.mel_embedding(audio_codes) + gpt.mel_pos_embedding(audio_codes)

    emb = torch.cat([cond_latents, text_emb, mel_emb], dim=1)
    attn_mask = torch.cat([attn_mask_cond, attn_mask_text, attn_mask_mel], dim=1)
    gpt_out = gpt.gpt(inputs_embeds=emb, return_dict=True, attention_mask=attn_mask)
    enc = gpt_out.last_hidden_state[:, offset:]
    enc = gpt.final_norm(enc)
    mel_latents = enc[:, -mel_emb.shape[1]:]             # (b, L, d)
    mel_logits = gpt.mel_head(mel_latents).permute(0, 2, 1)   # (b, C, L)

    for idx, l in enumerate(code_lengths):
        mel_targets[idx, l + 1:] = -1
    valid_mask = (mel_targets != -1)
    loss_mel = F.cross_entropy(mel_logits, mel_targets.long(), ignore_index=-1, label_smoothing=label_smoothing)
    return loss_mel, mel_logits, mel_latents, valid_mask


def build_student_gpt(cfg_model_args: dict, d_student: int = 640, heads: int = 10) -> nn.Module:
    """Build the Coqui GPT at the student width, then DELETE the speaker pathway (fixed-voice)."""
    from TTS.tts.layers.xtts.gpt import GPT
    a = cfg_model_args
    gpt = GPT(
        layers=a["gpt_layers"],
        model_dim=d_student,
        start_text_token=a["gpt_start_text_token"],
        stop_text_token=a["gpt_stop_text_token"],
        heads=heads,
        max_text_tokens=a["gpt_max_text_tokens"],
        max_mel_tokens=a["gpt_max_audio_tokens"],
        max_prompt_tokens=a["gpt_max_prompt_tokens"],
        number_text_tokens=a["gpt_number_text_tokens"],
        num_audio_tokens=a["gpt_num_audio_tokens"],
        start_audio_token=a["gpt_start_audio_token"],
        stop_audio_token=a["gpt_stop_audio_token"],
        use_perceiver_resampler=a["gpt_use_perceiver_resampler"],
        code_stride_len=a["gpt_code_stride_len"],
    )
    # fixed-voice: conditioning is baked + passed as cond_latents, so these modules are never used
    for attr in ("conditioning_encoder", "conditioning_perceiver", "conditioning_dropout"):
        if hasattr(gpt, attr):
            delattr(gpt, attr)
    return gpt
