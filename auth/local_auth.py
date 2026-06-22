import keyring
import hashlib
import time
import os
from loguru import logger

class LocalAuth:
    """Manages PIN-based authentication for JARVIS using the system keyring"""

    def __init__(self):
        self.service_name = "JARVIS_AUTH"
        self.username = "jarvis_user"
        self.max_attempts = 3
        self.lockout_time = 300  # 5 minutes in seconds
        self.lockfile = os.path.join(os.path.dirname(__file__), ".lockout")
        self.attempts = 0

    def _hash_pin(self, pin: str) -> str:
        """Returns SHA-256 hash of the PIN"""
        return hashlib.sha256(pin.encode()).hexdigest()

    def is_setup(self) -> bool:
        """Checks if a PIN has been set up previously"""
        return keyring.get_password(self.service_name, self.username) is not None

    def setup_pin(self, pin: str) -> bool:
        """Saves a new PIN to the keyring if valid"""
        # We strip any spaces just in case STT formats it as "12 34 56"
        clean_pin = pin.replace(" ", "")
        if not clean_pin.isdigit() or len(clean_pin) != 6:
            logger.error("PIN setup failed: PIN must be exactly 6 digits.")
            return False
            
        hashed = self._hash_pin(clean_pin)
        try:
            keyring.set_password(self.service_name, self.username, hashed)
            logger.info("New PIN securely saved to keyring.")
            return True
        except Exception as e:
            logger.error(f"Failed to save PIN to keyring: {e}")
            return False

    def check_lockout(self) -> float:
        """Returns remaining lockout time in seconds, or 0 if not locked"""
        if os.path.exists(self.lockfile):
            try:
                with open(self.lockfile, "r") as f:
                    lock_timestamp = float(f.read().strip())
                elapsed = time.time() - lock_timestamp
                if elapsed < self.lockout_time:
                    return self.lockout_time - elapsed
                else:
                    os.remove(self.lockfile)
                    self.attempts = 0
            except Exception:
                pass
        return 0.0

    def _apply_lockout(self):
        """Applies a 5-minute lockout"""
        try:
            with open(self.lockfile, "w") as f:
                f.write(str(time.time()))
            logger.warning(f"Maximum attempts reached. Locking authentication for {self.lockout_time // 60} minutes.")
        except Exception as e:
            logger.error(f"Failed to write lockfile: {e}")

    def verify_pin(self, pin: str) -> tuple[bool, str]:
        """
        Verifies a provided PIN against the stored hash.
        Returns a tuple of (Success, StatusMessage)
        """
        remaining_lock = self.check_lockout()
        if remaining_lock > 0:
            msg = f"System locked. Please try again in {int(remaining_lock)} seconds."
            logger.error(msg)
            return False, msg

        stored_hash = keyring.get_password(self.service_name, self.username)
        if not stored_hash:
            return False, "No PIN is currently set up."
            
        clean_pin = pin.replace(" ", "")
        if self._hash_pin(clean_pin) == stored_hash:
            self.attempts = 0
            if os.path.exists(self.lockfile):
                os.remove(self.lockfile)
            return True, "PIN verified successfully. Welcome back, sir."
        else:
            self.attempts += 1
            msg = f"Invalid PIN. Attempt {self.attempts} of {self.max_attempts}."
            logger.warning(msg)
            if self.attempts >= self.max_attempts:
                self._apply_lockout()
                msg = "Maximum attempts reached. System locked."
            return False, msg


if __name__ == "__main__":
    auth = LocalAuth()
    print("\n--- Testing JARVIS Local Auth Module ---")
    
    if not auth.is_setup():
        print("No PIN found in Keyring. Simulating setup with '123456'")
        auth.setup_pin("123456")
    else:
        print("PIN is already configured in the system keyring.")
        
    print("\nVerifying correct PIN '123456'...")
    success, msg = auth.verify_pin("123456")
    print(f"Result: {success} | Message: {msg}")

    print("\nVerifying wrong PIN '654321'...")
    success, msg = auth.verify_pin("654321")
    print(f"Result: {success} | Message: {msg}")
