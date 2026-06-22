import traceback
try:
    import mediapipe as mp
    print("mp version:", mp.__version__)
    print("Accessing mp.solutions:")
    print(mp.solutions)
    print("Success accessing mp.solutions!")
except Exception as e:
    print("Exception occurred:")
    traceback.print_exc()
