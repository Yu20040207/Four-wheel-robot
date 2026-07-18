// 更新系统状态
function updateStats() {
    fetch('/api/stats')
        .then(response => response.json())
        .then(data => {
            document.getElementById('clientCount').textContent = data.clients || 0;
            document.getElementById('frameCount').textContent = data.frames_received || 0;
            document.getElementById('fps').textContent = (data.fps || 0) + ' FPS';
            document.getElementById('latency').textContent = (data.latency || 0) + ' ms';
            document.getElementById('knownFaces').textContent = data.known_faces || 0;
            document.getElementById('loadedFaces').textContent = data.loaded_faces || 0;

            const statusElement = document.getElementById('recognitionStatus');
            if (data.recognition_enabled) {
                statusElement.textContent = '运行中';
                statusElement.style.color = '#28a745';
            } else {
                statusElement.textContent = '未启动';
                statusElement.style.color = '#dc3545';
            }

            // 更新采集状态
            const collectionStatus = document.getElementById('collectionStatus');
            const collectionProgress = document.getElementById('collectionProgress');

            if (data.face_collection_active) {
                collectionStatus.textContent = '采集中';
                collectionStatus.style.color = '#ffc107';
                collectionProgress.textContent = data.collection_progress;
            } else {
                collectionStatus.textContent = '空闲';
                collectionStatus.style.color = '#6c757d';
                collectionProgress.textContent = data.collection_progress;
            }
        })
        .catch(error => console.error('获取状态失败:', error));

    // 更新采集状态
    updateCollectionStatus();
}

// 更新人脸采集状态
function updateCollectionStatus(data) {
    console.log('更新采集状态，数据:', data);
    const collectionStatus = document.getElementById('collectionStatus');
    const collectionProgress = document.getElementById('collectionProgress');
    const progressContainer = document.getElementById('progressContainer');
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    const collectionMessage = document.getElementById('collectionMessage');

    if (!collectionStatus) {
        console.error('未找到采集状态元素');
    }
    if (!collectionProgress) {
        console.error('未找到采集进度元素');
    }
    if (!progressContainer) {
        console.error('未找到进度容器元素');
    }
    if (!progressFill) {
        console.error('未找到进度条元素');
    }
    if (!progressText) {
        console.error('未找到进度文本元素');
    }
    if (!collectionMessage) {
        console.error('未找到采集消息元素');
    }

            if (data.active) {
                messageElement.textContent = data.status_message;
                messageElement.style.color = '#ffc107';

                // 显示进度条
                progressContainer.style.display = 'block';
                const progress = (data.images_collected / data.total_images) * 100;
                progressFill.style.width = progress + '%';
                progressText.textContent = `采集进度: ${data.images_collected}/${data.total_images}`;

                // 禁用添加按钮
                addFaceButton.disabled = true;
                addFaceButton.textContent = '采集中...';

                // 如果采集完成，恢复按钮状态
                if (data.images_collected >= data.total_images || data.status_message.includes('完成') || data.status_message.includes('已达到最大')) {
                    setTimeout(() => {
                        progressContainer.style.display = 'none';
                        addFaceButton.disabled = false;
                        addFaceButton.textContent = '开始人脸采集';
                        messageElement.textContent = '采集完成！可以开始新的人脸采集。';
                        messageElement.style.color = '#28a745';
                        // 更新状态
                        updateStats();
                    }, 3000);
                }
            } else {
                // 隐藏进度条
                progressContainer.style.display = 'none';
                addFaceButton.disabled = false;
                addFaceButton.textContent = '开始人脸采集';

                if (data.status_message) {
                    messageElement.textContent = data.status_message;
                } else {
                    messageElement.textContent = '请输入姓名开始人脸采集。系统将自动检测人脸并拍摄5张照片，每张间隔2秒。';
                }
                messageElement.style.color = '#6c757d';
            }
        })
        .catch(error => console.error('获取采集状态失败:', error));
}

// 刷新视频流
function refreshStream() {
    fetch('/api/refresh_stream')
        .then(response => response.json())
        .then(data => {
            showMessage(data.message, 'success');
            // 重新加载视频流
            const videoElement = document.querySelector('.video-stream');
            videoElement.src = videoElement.src;
        })
        .catch(error => {
            showMessage('刷新视频流失败', 'error');
        });
}

function toggleFaceRecognition(action) {
    fetch(`/api/face_recognition/${action}`)
        .then(response => response.json())
        .then(data => {
            showMessage(data.message, data.status);
            updateStats();
        })
        .catch(error => {
            showMessage('操作失败', 'error');
        });
}

function reloadFaces() {
    fetch('/api/reload_faces')
        .then(response => response.json())
        .then(data => {
            showMessage(data.message, data.status);
            updateStats();
        })
        .catch(error => {
            showMessage('重新加载失败', 'error');
        });
}

function addFace() {
    const nameInput = document.getElementById('personName');
    const personName = nameInput.value.trim();

    if (!personName) {
        showMessage('请输入姓名', 'error');
        return;
    }

    fetch('/api/add_face', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ name: personName })
    })
    .then(response => response.json())
    .then(data => {
        showMessage(data.message, data.status);

        if (data.status === 'success') {
            nameInput.value = '';
            // 开始定期检查采集状态
            const checkInterval = setInterval(updateCollectionStatus, 1000);
            // 5分钟后停止检查（防止无限循环）
            setTimeout(() => clearInterval(checkInterval), 5 * 60 * 1000);
        }
    })
    .catch(error => {
        showMessage('添加失败: ' + error, 'error');
    });
}

// 显示消息提示
function showMessage(message, type) {
    const messageElement = document.getElementById('controlMessage');
    messageElement.textContent = message;
    messageElement.className = 'message ' + type;

    // 3秒后自动隐藏
    setTimeout(() => {
        messageElement.textContent = '';
        messageElement.className = 'message';
    }, 3000);
}

// 事件监听
document.addEventListener('DOMContentLoaded', function() {
    // 控制按钮
    document.getElementById('startRecognition').addEventListener('click', () => {
        toggleFaceRecognition('start');
    });

    document.getElementById('stopRecognition').addEventListener('click', () => {
        toggleFaceRecognition('stop');
    });

    document.getElementById('refreshStream').addEventListener('click', refreshStream);

    document.getElementById('reloadFaces').addEventListener('click', reloadFaces);

    document.getElementById('addFace').addEventListener('click', addFace);

    // 回车键添加人脸
    document.getElementById('personName').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            addFace();
        }
    });

    // 每2秒更新一次状态
    updateStats();
    setInterval(updateStats, 2000);

    // 每1秒更新一次采集状态
    setInterval(updateCollectionStatus, 1000);
});
