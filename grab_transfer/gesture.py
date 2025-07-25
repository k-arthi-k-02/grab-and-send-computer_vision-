import cv2
import mediapipe as mp

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

# Initialize MediaPipe Hands
hands = mp_hands.Hands(static_image_mode=False,
                       max_num_hands=1,
                       min_detection_confidence=0.5,
                       min_tracking_confidence=0.5)

# Indices for finger tips and their base joints
FINGER_TIPS = [4, 8, 12, 16, 20]
FINGER_BASES = [2, 5, 9, 13, 17]


def process_frame(frame):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands.process(rgb)
    hand_detected = False
    grab_detected = False
    if results.multi_hand_landmarks:
        hand_detected = True
        for hand_landmarks in results.multi_hand_landmarks:
            mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
            # Grab detection logic
            tip_folded = 0
            for tip_idx, base_idx in zip(FINGER_TIPS[1:], FINGER_BASES[1:]):  # skip thumb for simplicity
                tip = hand_landmarks.landmark[tip_idx]
                base = hand_landmarks.landmark[base_idx]
                if tip.y > base.y:  # Tip below base (folded)
                    tip_folded += 1
            if tip_folded >= 3:  # 3 or more fingers folded = grab
                grab_detected = True
    return frame, hand_detected, grab_detected 