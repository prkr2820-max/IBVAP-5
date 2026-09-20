import os
import cv2
import numpy as np
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, Response, jsonify, send_file, send_from_directory

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-secret-before-production')

VIDEO_PATH = os.environ.get(
    'DEMO_VIDEO',
    os.path.join(os.path.dirname(__file__), 'demo_input.mp4')
)

live_alerts = []

# Lightweight demo detector: OpenCV background subtraction. This keeps the public
# web demo small enough for low-memory hosts. The full YOLO/DeepFace/ALPR modules
# remain in the repository for local/GPU deployment.
background = cv2.createBackgroundSubtractorMOG2(history=120, varThreshold=42, detectShadows=True)
restrictedzone = np.array([[210, 145], [500, 145], [500, 330], [210, 330]], dtype=np.int32)
last_alert = None


def add_alert(message):
    global last_alert
    now = datetime.now().strftime('%H:%M:%S')
    if last_alert == message:
        return
    last_alert = message
    live_alerts.insert(0, {'time': now, 'msg': message, 'id': f'{now}-{len(live_alerts)}'})
    del live_alerts[50:]


def generate_demo_frames():
    cap = cv2.VideoCapture(VIDEO_PATH)
    if not cap.isOpened():
        return

    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    fps = cap.get(cv2.CAP_PROP_FPS) or 20
    delay = max(1, int(1000 / min(fps, 20)))
    frame_no = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            background.clear()
            continue

        frame_no += 1
        if frame.shape[1] > 960:
            scale = 960 / frame.shape[1]
            frame = cv2.resize(frame, (960, int(frame.shape[0] * scale)), interpolation=cv2.INTER_AREA)

        # Re-scale the restricted zone to the current frame.
        sx = frame.shape[1] / 960.0
        sy = frame.shape[0] / max(frame.shape[0], 1)
        zone = restrictedzone.copy()
        zone[:, 0] = (zone[:, 0] * sx).astype(int)
        zone[:, 1] = (zone[:, 1] * sy).astype(int)
        cv2.polylines(frame, [zone], True, (0, 0, 255), 2)
        cv2.putText(frame, 'IBVAP DEMO MODE', (18, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 102), 2)
        cv2.putText(frame, 'USER-PROVIDED DEMO VIDEO', (18, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 210, 255), 1)
        

        # Lightweight motion segmentation.
        small = cv2.resize(frame, (480, int(frame.shape[0] * 480 / frame.shape[1])))
        mask = background.apply(small)
        _, mask = cv2.threshold(mask, 210, 255, cv2.THRESH_BINARY)
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.dilate(mask, kernel, iterations=2)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        intruder = False
        for c in contours:
            area = cv2.contourArea(c)
            if area < 900:
                continue
            x, y, w, h = cv2.boundingRect(c)
            sx2 = frame.shape[1] / small.shape[1]
            sy2 = frame.shape[0] / small.shape[0]
            x1, y1, x2, y2 = int(x*sx2), int(y*sy2), int((x+w)*sx2), int((y+h)*sy2)
            cx, cy = (x1+x2)//2, (y1+y2)//2
            inside = cv2.pointPolygonTest(zone, (cx, cy), False) >= 0
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255) if not inside else (0, 0, 255), 2)
            cv2.putText(frame, 'MOVING OBJECT', (x1, max(18, y1-8)), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0,255,255), 1)
            if inside:
                intruder = True
                cv2.putText(frame, 'RESTRICTED ZONE INTRUSION', (x1, min(frame.shape[0]-10, y2+22)), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0,0,255), 2)

        if intruder and frame_no % 20 == 0:
            add_alert('RESTRICTED ZONE MOVEMENT DETECTED — HUMAN VERIFICATION REQUIRED')

        ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 72])
        if ret:
            yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n'

    cap.release()


@app.route('/')
def index():
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    return render_template('login.html')


@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username', '')
    password = request.form.get('password', '')
    valid_users = {'OF-0012', 'OF-0013', 'OF-0014', 'OF-0015', 'OF-0016'}
    expected_password = os.environ.get('DEMO_PASSWORD', 'ibvap123')
    if username in valid_users and password == expected_password:
        session['logged_in'] = True
        return redirect(url_for('dashboard'))
    return 'ACCESS DENIED: INVALID CLEARANCE KEY', 401


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    return render_template('dashboard.html')


@app.route('/demo-poster')
def static_demo_poster():
    poster = os.path.join(os.path.dirname(__file__), 'static_demo_poster.jpg')
    if not os.path.exists(poster):
        return 'Poster not found', 404
    return send_file(poster, mimetype='image/jpeg', max_age=3600)

@app.route('/demo-video')
def demo_video():
    if not session.get('logged_in'):
        return 'Unauthorized', 401
    if not os.path.exists(VIDEO_PATH):
        return 'Demo video not found', 404
    return send_file(VIDEO_PATH, mimetype='video/mp4', conditional=True, max_age=0)


@app.route('/stream/demo')
def stream_demo():
    if not session.get('logged_in'):
        return 'Unauthorized', 401
    return Response(generate_demo_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/get_alerts')
def get_alerts():
    if not session.get('logged_in'):
        return jsonify([])
    return jsonify(live_alerts[:50])


@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'mode': 'low-memory-demo'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False, threaded=True)
