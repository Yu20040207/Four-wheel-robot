// 安全更新 DOM 文本
function updateElementText(elementId, text) {
    const element = document.getElementById(elementId);
    if (element) {
        element.textContent = text;
    }
}

const BLACK_VIDEO_DATA_URI =
    'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

function getVideoStreamElement() {
    return document.getElementById('videoStream') || document.querySelector('.video-stream');
}

function hasVideoStream(data) {
    if (data && data.video_stream_active) {
        return true;
    }
    const fps = Number((data && (data.video_feed_fps || data.fps)) || 0);
    const frames = Number((data && data.frames_received) || 0);
    const img = getVideoStreamElement();
    const imgOk = !!(img && img.complete && img.naturalWidth > 16 && img.naturalHeight > 16
        && !String(img.src || '').startsWith('data:'));
    return fps > 0 || frames > 0 || imgOk;
}

function isCameraActive(data) {
    if (window.__cameraUiState === true) {
        return true;
    }
    if (window.__cameraUiState === false) {
        return false;
    }
    if (data && data.openmv_camera_active) {
        return true;
    }
    return hasVideoStream(data);
}

function syncCameraUiState(data) {
    if (!data) {
        return;
    }
    if (window.__cameraUiState === true && data.openmv_camera_active) {
        window.__cameraUiState = null;
    } else if (window.__cameraUiState === false && !data.openmv_camera_active && !hasVideoStream(data)) {
        window.__cameraUiState = null;
    }
}

function applyCameraUiState(on) {
    window.__cameraUiState = on;
    const prev = window.__lastStatsData || {};
    const merged = Object.assign({}, prev, {
        openmv_camera_active: on,
        openmv_face_tracking_active: on ? !!prev.openmv_face_tracking_active : false
    });
    if (!on) {
        window.__faceTrackingUiState = false;
    }
    window.__lastStatsData = merged;
    updateControlPanelButtons(merged);
}

function isRecognitionRunning(data) {
    return !!(data && (data.recognition_enabled || data.recognition_status === 'running'));
}

function isFaceTrackingActive(data) {
    if (window.__faceTrackingUiState === true) {
        return true;
    }
    if (window.__faceTrackingUiState === false) {
        return false;
    }
    if (data && data.openmv_face_tracking_active !== undefined && data.openmv_face_tracking_active !== null) {
        return !!data.openmv_face_tracking_active;
    }
    return false;
}

function syncFaceTrackingUiState(data) {
    if (!data) {
        return;
    }
    if (window.__faceTrackingUiState === true && data.openmv_face_tracking_active) {
        window.__faceTrackingUiState = null;
    } else if (window.__faceTrackingUiState === false && !data.openmv_face_tracking_active) {
        window.__faceTrackingUiState = null;
    }
}

function applyFaceTrackingUiState(on) {
    window.__faceTrackingUiState = on;
    const merged = Object.assign({}, window.__lastStatsData || {}, {
        openmv_face_tracking_active: on,
        openmv_system_state: on ? 3 : 2
    });
    window.__lastStatsData = merged;
    updateControlPanelButtons(merged);
}

function updateHeadServoAnglesDisplay(data, faceTrackOn) {
    const anglesEl = document.getElementById('headServoAngles');
    if (!anglesEl) {
        return;
    }
    if (faceTrackOn) {
        const pan = data.head_pan_angle != null ? Number(data.head_pan_angle).toFixed(1) : '--';
        const tilt = data.head_tilt_angle != null ? Number(data.head_tilt_angle).toFixed(1) : '--';
        anglesEl.textContent = '头部舵机  偏航(左右): ' + pan + '°   俯仰(上下): ' + tilt + '°';
        anglesEl.style.display = 'block';
    } else {
        anglesEl.textContent = '';
        anglesEl.style.display = 'none';
    }
}

function showBlackVideo() {
    const img = getVideoStreamElement();
    if (!img) {
        return;
    }
    img.src = BLACK_VIDEO_DATA_URI;
    img.style.backgroundColor = '#000';
}

function refreshVideoStreamSrc() {
    const img = getVideoStreamElement();
    if (!img) {
        return;
    }
    img.style.backgroundColor = '';
    const base = img.getAttribute('data-feed-base') || '/video_feed';
    const robot = (window.RobotControl && window.RobotControl.selectedId)
        || (window.__lastStatsData && window.__lastStatsData.selected_robot_id);
    if (robot) {
        img.src = base + '?robot=' + encodeURIComponent(robot) + '&t=' + Date.now();
    } else {
        img.src = base + '?t=' + Date.now();
    }
}

function updateControlPanelButtons(data) {
    data = data || window.__lastStatsData || {};
    window.__lastStatsData = data;
    syncCameraUiState(data);
    syncFaceTrackingUiState(data);

    const cameraOn = isCameraActive(data);
    const streamOk = hasVideoStream(data);
    const recOn = isRecognitionRunning(data);
    const faceTrackOn = isFaceTrackingActive(data);

    const openBtn = document.getElementById('openCamera');
    if (openBtn && openBtn.dataset.busy !== '1') {
        openBtn.textContent = '打开摄像头';
        openBtn.className = 'btn btn-info';
        openBtn.disabled = false;
        openBtn.removeAttribute('title');
    }

    const recBtn = document.getElementById('startRecognition');
    if (recBtn && recBtn.dataset.busy !== '1') {
        recBtn.textContent = recOn ? '停止人脸识别' : '启用人脸识别';
        recBtn.className = recOn ? 'btn btn-secondary' : 'btn btn-primary';
        if (recOn) {
            recBtn.disabled = false;
            recBtn.removeAttribute('title');
        } else if (!cameraOn || !streamOk) {
            recBtn.disabled = true;
            recBtn.title = '未收到视频流';
        } else {
            recBtn.disabled = false;
            recBtn.removeAttribute('title');
        }
    }

    const stopBtn = document.getElementById('stopRecognition');
    if (stopBtn) {
        stopBtn.style.display = 'none';
    }

    const pickupBtn = document.getElementById('pickupGarbage');
    if (pickupBtn) {
        const garbageOn = !!(data.garbage_tracking_enabled);
        pickupBtn.textContent = garbageOn ? '停止捡取' : '拾取前方垃圾';
        pickupBtn.className = garbageOn ? 'btn btn-secondary' : 'btn btn-success';
    }

    const faceTrackBtn = document.getElementById('toggleFaceTracking');
    if (faceTrackBtn && faceTrackBtn.dataset.busy !== '1') {
        faceTrackBtn.textContent = faceTrackOn ? '关闭跟踪人脸' : '开启跟踪人脸';
        faceTrackBtn.className = faceTrackOn ? 'btn btn-secondary' : 'btn btn-primary';
        if (faceTrackOn) {
            faceTrackBtn.disabled = false;
            faceTrackBtn.removeAttribute('title');
        } else if (!cameraOn || !streamOk) {
            faceTrackBtn.disabled = true;
            faceTrackBtn.title = '未收到视频流';
        } else {
            faceTrackBtn.disabled = false;
            faceTrackBtn.removeAttribute('title');
        }
    }

    updateHeadServoAnglesDisplay(data, faceTrackOn);

    setStatRunning('recognitionStatus', '运行中', '未启动', recOn);
}

window.updateControlPanelButtons = updateControlPanelButtons;
window.hasVideoStream = hasVideoStream;

function setStatRunning(elementId, runningText, stoppedText, isRunning) {
    const element = document.getElementById(elementId);
    if (!element) {
        return;
    }
    element.textContent = isRunning ? runningText : stoppedText;
    element.className = isRunning ? 'stat-value status-running' : 'stat-value';
}

// 更新系统状态（首页仪表盘）
function updateStats() {
    if (typeof window.refreshSystemStatus === 'function') {
        return window.refreshSystemStatus().catch(function (error) {
            console.error('获取状态失败:', error);
        });
    }

    fetch('/api/stats', { cache: 'no-store' })
        .then(response => {
            if (!response.ok) {
                throw new Error('网络响应不正常');
            }
            return response.json();
        })
        .then(data => {
            try {
                applyStatsData(data);
            } catch (error) {
                console.error('更新状态 DOM 失败:', error);
            }
        })
        .catch(error => console.error('获取状态失败:', error));
}

function applyStatsData(data) {
    updateElementText('clientCount', data.clients || 0);
    updateElementText('frameCount', data.frames_received || 0);
    updateElementText('fps', (data.fps || 0).toFixed(1));
    updateElementText('knownFaces', data.known_faces || 0);
    updateElementText('loadedFaces', data.loaded_faces || 0);

    const latencyEl = document.getElementById('latency');
    if (latencyEl) {
        latencyEl.textContent = (data.latency || 0) + ' ms';
    }

    updateElementText('humanDetectionStat', data.human_tracking_enabled ? '开启' : '关闭');
    updateElementText('humanTrackingStat', data.human_tracking_active ? '跟踪中' : '关闭');
    updateElementText('humanDetectionStatus', data.human_tracking_enabled ? '启用' : '未启用');
    updateElementText('humanDetectedCount', data.humans_detected || 0);
    updateElementText(
        'totalHumansDetected',
        (data.human_tracking_stats && data.human_tracking_stats.total_humans_detected) || 0
    );
    updateElementText('humanTrackingStatus', data.human_tracking_active ? '跟踪中' : '未启用');
    updateElementText('humanTrackingCount', data.humans_tracking || 0);

    const garbageOn = !!(data.garbage_tracking_enabled);
    const garbagePickupBusy = !!(data.garbage_pickup_in_progress);
    updateElementText('garbageTrackingStat', garbageOn ? (garbagePickupBusy ? '捡取中' : '检测中') : '关闭');
    updateControlPanelButtons(data);

    const currentTargetElement = document.getElementById('currentHumanTarget');
    if (currentTargetElement) {
        if (data.current_human_target && data.current_human_target.id !== undefined) {
            currentTargetElement.textContent = 'ID: ' + data.current_human_target.id;
        } else {
            currentTargetElement.textContent = '无';
        }
    }

    setStatRunning('mqttStatus', '已连接', '断开', !!(data.robot_connected || data.mqtt_connected));
    if (typeof window.syncRobotConnectionState === 'function') {
        window.syncRobotConnectionState(data);
    }

    const recognitionRunning = isRecognitionRunning(data);
    setStatRunning('recognitionStatus', '运行中', '未启动', recognitionRunning);

    updateCollectionStatusFromStats(data);

    fetch('/api/flask_status')
        .then(response => response.json())
        .then(flaskData => {
            setStatRunning(
                'flaskRecognitionStatus',
                '运行中',
                '未启动',
                !!flaskData.recognition_enabled
            );
        })
        .catch(error => console.error('获取Flask状态失败:', error));
}

function updateCollectionStatusFromStats(data) {
    const collectionStatus = document.getElementById('collectionStatus');
    const collectionProgress = document.getElementById('collectionProgress');
    const progressContainer = document.getElementById('progressContainer');
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    const collectionMessage = document.getElementById('collectionMessage');
    const addFaceBtn = document.getElementById('addFace');
    const cancelCollectionBtn = document.getElementById('cancelCollection');

    if (!collectionStatus || !collectionProgress) {
        return;
    }

    if (data.face_collection_active) {
        collectionStatus.textContent = '采集中';
        collectionStatus.className = 'stat-value status-collecting';
        collectionProgress.textContent = data.collection_progress || '0/5';

        if (progressContainer) {
            progressContainer.style.display = 'block';
        }

        if (progressFill && progressText) {
            const progress = data.collection_progress ? data.collection_progress.split('/') : ['0', '5'];
            const current = parseInt(progress[0], 10) || 0;
            const total = parseInt(progress[1], 10) || 5;
            const percentage = total > 0 ? (current / total) * 100 : 0;
            progressFill.style.width = percentage + '%';
            progressText.textContent = '采集进度: ' + current + '/' + total;
        }

        fetch('/api/collection_status')
            .then(response => response.json())
            .then(collectionData => {
                if (collectionMessage) {
                    collectionMessage.textContent = collectionData.status_message || '正在采集人脸数据...';
                }
            })
            .catch(error => console.error('获取采集状态失败:', error));

        if (addFaceBtn) {
            addFaceBtn.disabled = true;
        }
        if (cancelCollectionBtn) {
            cancelCollectionBtn.disabled = false;
            cancelCollectionBtn.style.display = 'inline-block';
        }
    } else {
        collectionStatus.textContent = '空闲';
        collectionStatus.className = 'stat-value';
        collectionProgress.textContent = '0/5';

        if (progressContainer) {
            progressContainer.style.display = 'none';
        }
        if (collectionMessage) {
            collectionMessage.textContent =
                '请输入姓名开始人脸采集。系统将自动检测人脸并拍摄5张照片，每张间隔2秒。';
        }
        if (addFaceBtn) {
            addFaceBtn.disabled = false;
        }
        if (cancelCollectionBtn) {
            cancelCollectionBtn.disabled = true;
            cancelCollectionBtn.style.display = 'none';
        }
    }
}

// 兼容旧页面：单独拉取采集状态
function updateCollectionStatus() {
    fetch('/api/collection_status')
        .then(response => response.json())
        .then(data => {
            updateCollectionStatusFromStats({
                face_collection_active: data.active,
                collection_progress: `${data.images_collected || 0}/${data.total_images || 5}`
            });

            const addFaceButton = document.getElementById('addFace');
            const collectionMessage = document.getElementById('collectionMessage');
            if (data.active && addFaceButton) {
                addFaceButton.disabled = true;
                addFaceButton.textContent = '采集中...';
            } else if (addFaceButton) {
                addFaceButton.disabled = false;
                addFaceButton.textContent = '开始人脸采集';
            }
            if (collectionMessage && data.status_message) {
                collectionMessage.textContent = data.status_message;
            }
        })
        .catch(error => console.error('获取采集状态失败:', error));
}

function showMessage(message, type) {
    const messageElement = document.getElementById('controlMessage');
    if (!messageElement) {
        return;
    }
    messageElement.textContent = message;
    messageElement.className = 'message ' + (type === 'success' ? 'success' : type === 'error' ? 'error' : type);
    setTimeout(() => {
        messageElement.textContent = '';
        messageElement.className = 'message';
    }, 3000);
}

function parseApiResponse(response) {
    return response.json().then(function (data) {
        if (!response.ok && data && data.message) {
            throw new Error(data.message);
        }
        return data;
    });
}

function requireRobotOrAbort(showMsg) {
    if (typeof window.requireRobotSelected === 'function') {
        return window.requireRobotSelected(showMsg);
    }
    return true;
}

function showHumanTrackingMessage(message, type) {
    const messageDiv = document.getElementById('humanTrackingMessage');
    if (!messageDiv) {
        return;
    }
    messageDiv.textContent = message;
    messageDiv.className = type === 'success' ? 'message success' : 'message error';
    setTimeout(() => {
        messageDiv.textContent = '';
        messageDiv.className = 'message';
    }, 3000);
}

function refreshStream() {
    if (!requireRobotOrAbort()) return;
    fetch('/api/refresh_stream')
        .then(parseApiResponse)
        .then(data => {
            showMessage(data.message, 'success');
            const videoElement = document.getElementById('videoStream') || document.querySelector('.video-stream');
            if (videoElement) {
                videoElement.src = videoElement.src.split('?')[0] + '?t=' + Date.now();
            }
        })
        .catch(error => showMessage(error.message || '刷新视频流失败', 'error'));
}

function toggleFaceTracking() {
    if (!requireRobotOrAbort()) return;

    const trackBtn = document.getElementById('toggleFaceTracking');
    const data = window.__lastStatsData || {};
    const faceTrackOn = isFaceTrackingActive(data);

    if (!faceTrackOn && !hasVideoStream(data)) {
        showMessage('未收到视频流', 'error');
        return;
    }

    const action = faceTrackOn ? 'stop' : 'start';
    const busyLabel = faceTrackOn ? '关闭中...' : '开启中...';
    if (trackBtn) {
        trackBtn.dataset.busy = '1';
        trackBtn.textContent = busyLabel;
        trackBtn.disabled = true;
    }

    fetch('/api/face_tracking/' + action)
        .then(parseApiResponse)
        .then(result => {
            applyFaceTrackingUiState(!faceTrackOn);
            showMessage(result.message, result.status);
            if (typeof window.refreshSystemStatus === 'function') {
                return window.refreshSystemStatus();
            }
            updateStats();
        })
        .catch(error => {
            window.__faceTrackingUiState = null;
            showMessage(error.message || '人脸跟踪操作失败', 'error');
        })
        .finally(() => {
            if (trackBtn) {
                delete trackBtn.dataset.busy;
                updateControlPanelButtons(window.__lastStatsData || {});
            }
            if (typeof window.refreshSystemStatus === 'function') {
                window.refreshSystemStatus();
            } else {
                updateStats();
            }
        });
}

function toggleFaceRecognition() {
    if (!requireRobotOrAbort()) return;

    const recBtn = document.getElementById('startRecognition');
    const data = window.__lastStatsData || {};
    const recOn = isRecognitionRunning(data);

    if (!recOn && !hasVideoStream(data)) {
        showMessage('未收到视频流', 'error');
        return;
    }

    const action = recOn ? 'stop' : 'start';
    const busyLabel = recOn ? '停止中...' : '启用中...';
    if (recBtn) {
        recBtn.dataset.busy = '1';
        recBtn.textContent = busyLabel;
        recBtn.disabled = true;
    }

    fetch('/api/face_recognition/' + action)
        .then(parseApiResponse)
        .then(result => {
            showMessage(result.message, result.status);
            if (typeof window.refreshSystemStatus === 'function') {
                return window.refreshSystemStatus();
            }
            updateStats();
        })
        .catch(error => showMessage(error.message || '操作失败', 'error'))
        .finally(() => {
            if (recBtn) {
                delete recBtn.dataset.busy;
            }
            if (typeof window.refreshSystemStatus === 'function') {
                window.refreshSystemStatus();
            } else {
                updateStats();
            }
        });
}

function reloadFaces() {
    if (!requireRobotOrAbort()) return;
    fetch('/api/reload_faces')
        .then(parseApiResponse)
        .then(data => {
            showMessage(data.message, data.status);
            if (typeof window.refreshSystemStatus === 'function') {
                window.refreshSystemStatus();
            } else {
                updateStats();
            }
        })
        .catch(error => showMessage(error.message || '重新加载失败', 'error'));
}

function controlHumanTracking(action) {
    if (!requireRobotOrAbort(false)) {
        showHumanTrackingMessage('请先在顶部选择要控制的机器人', 'error');
        return;
    }
    fetch('/api/human_tracking/' + action)
        .then(parseApiResponse)
        .then(data => {
            showHumanTrackingMessage(data.message, data.status);
            if (typeof window.refreshSystemStatus === 'function') {
                window.refreshSystemStatus();
            } else {
                updateStats();
            }
            const videoImg = document.getElementById('videoStream');
            if (videoImg) {
                videoImg.src = videoImg.src.split('?')[0] + '?t=' + Date.now();
            }
        })
        .catch(error => showHumanTrackingMessage(error.message || ('请求失败: ' + error.message), 'error'));
}

function openCamera() {
    if (!requireRobotOrAbort()) return;

    const openBtn = document.getElementById('openCamera');
    if (openBtn) {
        openBtn.dataset.busy = '1';
        openBtn.textContent = '打开中...';
        openBtn.disabled = true;
    }

    fetch('/api/camera/open')
        .then(parseApiResponse)
        .then(result => {
            applyCameraUiState(true);
            showMessage(result.message, result.status);
            refreshVideoStreamSrc();
            if (typeof window.refreshSystemStatus === 'function') {
                return window.refreshSystemStatus();
            }
            updateStats();
        })
        .catch(error => {
            window.__cameraUiState = null;
            showMessage(error.message || '打开摄像头失败', 'error');
        })
        .finally(() => {
            if (openBtn) {
                delete openBtn.dataset.busy;
                openBtn.textContent = '打开摄像头';
                openBtn.disabled = false;
            }
            if (typeof window.refreshSystemStatus === 'function') {
                window.refreshSystemStatus();
            } else {
                updateStats();
            }
        });
}

function controlGarbagePickup(action) {
    if (!requireRobotOrAbort()) return;
    fetch('/api/garbage_pickup/' + action)
        .then(parseApiResponse)
        .then(data => {
            showMessage(data.message, data.status);
            if (typeof window.refreshSystemStatus === 'function') {
                window.refreshSystemStatus();
            } else {
                updateStats();
            }
            const videoImg = document.getElementById('videoStream');
            if (videoImg) {
                videoImg.src = videoImg.src.split('?')[0] + '?t=' + Date.now();
            }
        })
        .catch(error => showMessage(error.message || ('请求失败: ' + error.message), 'error'));
}

function toggleGarbagePickup() {
    const pickupBtn = document.getElementById('pickupGarbage');
    const isRunning = pickupBtn && pickupBtn.textContent === '停止捡取';
    controlGarbagePickup(isRunning ? 'stop' : 'start');
}

function sendRecognitionResult() {
    if (!requireRobotOrAbort()) return;
    fetch('/api/send_recognition_result')
        .then(parseApiResponse)
        .then(data => {
            const statusDiv = document.getElementById('recognitionResultStatus');
            if (statusDiv) {
                statusDiv.textContent = data.message;
                statusDiv.className = data.status === 'success' ? 'status-success' : 'status-error';
                setTimeout(() => {
                    statusDiv.textContent = '';
                }, 3000);
            }
        })
        .catch(error => console.error('发送识别结果失败:', error));
}

function saveRubbishPhoto() {
    if (!requireRobotOrAbort()) return;
    const saveBtn = document.getElementById('saveRubbishPhoto');
    const defaultText = '保存截图';
    if (!saveBtn || saveBtn.disabled) {
        return;
    }

    saveBtn.textContent = '保存中...';
    saveBtn.disabled = true;

    fetch('/api/save_rubbish_photo', { method: 'POST' })
        .then(response => response.json().then(data => ({ ok: response.ok, data })))
        .then(({ ok, data }) => {
            if (ok && data.status === 'success') {
                showMessage(data.message, 'success');
                saveBtn.textContent = defaultText;
                saveBtn.disabled = false;
                return;
            }
            showMessage(data.message || '保存失败', 'error');
            saveBtn.textContent = '保存失败';
            setTimeout(() => {
                saveBtn.textContent = defaultText;
                saveBtn.disabled = false;
            }, 3000);
        })
        .catch(error => {
            showMessage('保存截图失败: ' + error.message, 'error');
            saveBtn.textContent = '保存失败';
            setTimeout(() => {
                saveBtn.textContent = defaultText;
                saveBtn.disabled = false;
            }, 3000);
        });
}

function ensureControlPanelButtons() {
    const reloadBtn = document.getElementById('reloadFaces');
    if (!reloadBtn || !reloadBtn.parentNode) {
        return;
    }
    if (!document.getElementById('saveRubbishPhoto')) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.id = 'saveRubbishPhoto';
        btn.className = 'btn btn-warning';
        btn.textContent = '保存截图';
        reloadBtn.insertAdjacentElement('afterend', btn);
    }
    const saveBtn = document.getElementById('saveRubbishPhoto');
    if (saveBtn && !document.getElementById('openCamera')) {
        const openCamBtn = document.createElement('button');
        openCamBtn.type = 'button';
        openCamBtn.id = 'openCamera';
        openCamBtn.className = 'btn btn-info';
        openCamBtn.textContent = '打开摄像头';
        saveBtn.insertAdjacentElement('afterend', openCamBtn);
    }
    const openCamBtn = document.getElementById('openCamera');
    if (openCamBtn && !document.getElementById('pickupGarbage')) {
        const pickupBtn = document.createElement('button');
        pickupBtn.type = 'button';
        pickupBtn.id = 'pickupGarbage';
        pickupBtn.className = 'btn btn-success';
        pickupBtn.textContent = '拾取前方垃圾';
        openCamBtn.insertAdjacentElement('afterend', pickupBtn);
    }
    const pickupBtn = document.getElementById('pickupGarbage');
    if (pickupBtn && !document.getElementById('toggleFaceTracking')) {
        const trackBtn = document.createElement('button');
        trackBtn.type = 'button';
        trackBtn.id = 'toggleFaceTracking';
        trackBtn.className = 'btn btn-primary';
        trackBtn.textContent = '开启跟踪人脸';
        pickupBtn.insertAdjacentElement('afterend', trackBtn);
    }
    const panel = document.querySelector('.video-section .control-panel');
    if (panel && !document.getElementById('headServoAngles')) {
        const anglesEl = document.createElement('div');
        anglesEl.id = 'headServoAngles';
        anglesEl.className = 'head-servo-angles';
        anglesEl.style.display = 'none';
        panel.insertAdjacentElement('afterend', anglesEl);
    }
}

function addFace() {
    if (!requireRobotOrAbort()) return;
    const nameInput = document.getElementById('personName');
    if (!nameInput) {
        return;
    }
    const personName = nameInput.value.trim();
    if (!personName) {
        showMessage('请输入姓名', 'error');
        return;
    }

    fetch('/api/add_face', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: personName })
    })
        .then(parseApiResponse)
        .then(data => {
            showMessage(data.message, data.status);
            if (data.status === 'success') {
                nameInput.value = '';
            }
            if (typeof window.refreshSystemStatus === 'function') {
                window.refreshSystemStatus();
            } else {
                updateStats();
            }
        })
        .catch(error => showMessage(error.message || ('添加失败: ' + error), 'error'));
}

function cancelCollection() {
    if (!requireRobotOrAbort()) return;
    fetch('/api/cancel_collection', { method: 'POST' })
        .then(parseApiResponse)
        .then(data => {
            showMessage(data.message, data.status);
            if (typeof window.refreshSystemStatus === 'function') {
                window.refreshSystemStatus();
            } else {
                updateStats();
            }
        })
        .catch(error => showMessage('取消采集失败: ' + error.message, 'error'));
}

function bindIndexPageEvents() {
    ensureControlPanelButtons();

    const bindings = [
        ['startRecognition', toggleFaceRecognition],
        ['refreshStream', refreshStream],
        ['reloadFaces', reloadFaces],
        ['saveRubbishPhoto', saveRubbishPhoto],
        ['openCamera', openCamera],
        ['pickupGarbage', toggleGarbagePickup],
        ['toggleFaceTracking', toggleFaceTracking],
        ['addFace', addFace],
        ['cancelCollection', cancelCollection],
        ['sendRecognitionBtn', sendRecognitionResult],
        ['startHumanDetection', () => controlHumanTracking('start_detection')],
        ['startHumanTracking', () => controlHumanTracking('start_tracking')],
        ['stopHumanTracking', () => controlHumanTracking('stop_tracking')],
        ['disableHumanTracking', () => controlHumanTracking('disable')]
    ];

    bindings.forEach(([id, handler]) => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('click', handler);
        }
    });

    const personNameEl = document.getElementById('personName');
    if (personNameEl) {
        personNameEl.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                addFace();
            }
        });
    }
}

let statsUpdateInterval = null;

document.addEventListener('DOMContentLoaded', function() {
    bindIndexPageEvents();
    const videoImg = getVideoStreamElement();
    if (videoImg) {
        videoImg.addEventListener('load', function() {
            if (window.__lastStatsData && typeof window.updateControlPanelButtons === 'function') {
                window.updateControlPanelButtons(window.__lastStatsData);
            }
        });
    }
    if (typeof updateRobotControlUI === 'function') {
        updateRobotControlUI();
    }
    updateStats();
    if (statsUpdateInterval) {
        clearInterval(statsUpdateInterval);
    }
    statsUpdateInterval = setInterval(updateStats, 1000);
});

window.addEventListener('beforeunload', function() {
    if (statsUpdateInterval) {
        clearInterval(statsUpdateInterval);
    }
});
