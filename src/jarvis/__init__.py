"""JARVIS - a privacy-first desktop voice and vision assistant.

Deliberately empty of imports. Importing submodules here would make
`import jarvis.services.timeparse` pull in PyQt6, MediaPipe, and the audio
stack, undoing the property that lets the test suite run on a headless
Linux runner with only requirements-test.txt installed.
"""

__version__ = "1.0.0"
