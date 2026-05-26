// const socket = io('/');  // 确保连接到默认命名空间
const socket = io('http://YOUR_SERVER_IP:5050/', { // 替换为实际服务器 IP
  reconnection: true,
  reconnectionAttempts: 5,
  reconnectionDelay: 1000,
  timeout: 5000
});
let scene, camera, renderer, cube;
let accCtx, accChart, gyroChart;
let filterEnabled = true;
let timeData = [], accXData = [], accYData = [], accZData = [], gyroXData = [], gyroYData = [], gyroZData = [];
let startTime = Date.now();

// Socket.IO 连接状态
socket.on('connect', () => {
  console.log('Socket.IO 连接成功, socket.id:', socket.id);
  document.getElementById('connectionInfo').innerText = 'Connected to Socket.IO';
  document.getElementById('connectionInfo').style.color = 'lightgreen';
});

socket.on('connect_error', (error) => {
  console.error('Socket.IO 连接失败:', error.message);
  document.getElementById('connectionInfo').innerText = `Socket.IO connection failed: ${error.message}`;
  document.getElementById('connectionInfo').style.color = 'red';
});

socket.on('disconnect', () => {
  console.log('Socket.IO 断开连接');
  document.getElementById('connectionInfo').innerText = 'Socket.IO disconnected';
  document.getElementById('connectionInfo').style.color = 'red';
});

socket.on('reconnect', (attempt) => {
  console.log(`Socket.IO 重新连接, 尝试次数: ${attempt}`);
  document.getElementById('connectionInfo').innerText = 'Socket.IO reconnected';
  document.getElementById('connectionInfo').style.color = 'lightgreen';
});


socket.onAny((event, ...args) => {
  console.log(`收到 Socket.IO 事件: ${event}`, args);
});

socket.on('test_event', (data) => {
  console.log('收到 test_event:', data);
});

// SocketIO listener
console.log('注册 sensor_data 监听器');
socket.on('sensor_data', (data) => {
  console.log('收到 sensor_data:', data);
  updateVisualization(data);
});

// Initialize 3D scene for orientation
function init3D() {
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(75, 1, 0.1, 1000);
  renderer = new THREE.WebGLRenderer({antialias: true});
  renderer.setSize(400, 400);
  document.getElementById('orientation').appendChild(renderer.domElement);

  const geometry = new THREE.BoxGeometry(10, 10, 2);
  const materials = [
    new THREE.MeshBasicMaterial({color: 0x1f77b4}),
    new THREE.MeshBasicMaterial({color: 0x1f77b4}),
    new THREE.MeshBasicMaterial({color: 0xff7f0e}),
    new THREE.MeshBasicMaterial({color: 0x2ca02c}),
    new THREE.MeshBasicMaterial({color: 0xd62728}),
    new THREE.MeshBasicMaterial({color: 0x9467bd})
  ];
  cube = new THREE.Mesh(geometry, materials);
  scene.add(cube);

  scene.add(new THREE.AxesHelper(15));

  camera.position.set(0, 0, 20);
  camera.lookAt(0, 0, 0);
}

// Initialize 2D acceleration vector canvas
function initAccVector() {
  const canvas = document.getElementById('accVectorCanvas');
  accCtx = canvas.getContext('2d');
}

// Initialize charts
function initCharts() {
  if (typeof Chart === 'undefined') {
    console.error('Chart.js 未定义，请检查是否正确加载');
    return;
  }
  Chart.register(Chart.LineController, Chart.LineElement, Chart.PointElement, Chart.LinearScale, Chart.Title);

  const accChartCtx = document.getElementById('accChart').getContext('2d');
  accChart = new Chart(accChartCtx, {
    type: 'line',
    data: {
      labels: timeData,
      datasets: [
        {label: 'X', data: accXData, borderColor: 'red'},
        {label: 'Y', data: accYData, borderColor: 'green'},
        {label: 'Z', data: accZData, borderColor: 'blue'}
      ]
    },
    options: {
      responsive: true,
      scales: {x: {type: 'linear', title: {display: true, text: 'Time (s)'}}}
    }
  });

  const gyroChartCtx = document.getElementById('gyroChart').getContext('2d');
  gyroChart = new Chart(gyroChartCtx, {
    type: 'line',
    data: {
      labels: timeData,
      datasets: [
        {label: 'X', data: gyroXData, borderColor: 'red'},
        {label: 'Y', data: gyroYData, borderColor: 'green'},
        {label: 'Z', data: gyroZData, borderColor: 'blue'}
      ]
    },
    options: {
      responsive: true,
      scales: {x: {type: 'linear', title: {display: true, text: 'Time (s)'}}}
    }
  });
  console.log('图表初始化完成');
}

// Update function
let lastData = null;

function updateVisualization(data) {
  console.log('更新可视化数据:', data);
  try {
    lastData = data; // 保存最新数据
    if (filterEnabled) {
      cube.rotation.x = THREE.MathUtils.degToRad(data.pitch);
      cube.rotation.y = THREE.MathUtils.degToRad(data.roll);
      cube.rotation.z = THREE.MathUtils.degToRad(data.yaw);
    } else {
      const ax = data.acceleration_x, ay = data.acceleration_y, az = data.acceleration_z;
      const pitch = Math.atan2(-ax, Math.sqrt(ay * ay + az * az));
      const roll = Math.atan2(ay, az);
      cube.rotation.x = pitch;
      cube.rotation.y = roll;
      cube.rotation.z = 0;
    }
    renderer.render(scene, camera);
    console.log('3D 模型更新完成');

    accCtx.clearRect(0, 0, 400, 400);
    accCtx.beginPath();
    accCtx.moveTo(200, 200);
    accCtx.lineTo(200 + data.acceleration_x * 20, 200 + data.acceleration_y * 20);
    accCtx.strokeStyle = 'cyan';
    accCtx.lineWidth = 5;
    accCtx.stroke();
    console.log('加速度向量更新完成');

    const accMag = Math.sqrt(data.acceleration_x ** 2 + data.acceleration_y ** 2 + data.acceleration_z ** 2);
    document.getElementById('accText').innerText = `Acceleration:\nX: ${data.acceleration_x.toFixed(2)} m/s²\nY: ${data.acceleration_y.toFixed(2)} m/s²\nZ: ${data.acceleration_z.toFixed(2)} m/s²\nMag: ${accMag.toFixed(2)} m/s²`;
    console.log('加速度文本更新完成');

    document.getElementById('sensorInfo').innerText = `Gyroscope:\nX: ${data.gyro_x.toFixed(2)} rad/s\nY: ${data.gyro_y.toFixed(2)} rad/s\nZ: ${data.gyro_z.toFixed(2)} rad/s\n\nOrientation:\nPitch: ${data.pitch.toFixed(2)}°\nRoll: ${data.roll.toFixed(2)}°\nYaw: ${data.yaw.toFixed(2)}°\n\nTemperature: ${data.temperature.toFixed(2)}°C`;
    console.log('传感器信息更新完成');

    document.getElementById('timeInfo').innerText = `Last Update: ${new Date().toLocaleString()}`;
    document.getElementById('connectionInfo').innerText = 'Connected to device';
    document.getElementById('connectionInfo').style.color = 'lightgreen';
    document.getElementById('filterInfo').innerText = `Filter: ${filterEnabled ? 'ON' : 'OFF'}`;
    document.getElementById('filterInfo').style.color = filterEnabled ? 'lightgreen' : 'red';

    const currentTime = (Date.now() - startTime) / 1000;
    timeData.push(currentTime);
    accXData.push(data.acceleration_x);
    accYData.push(data.acceleration_y);
    accZData.push(data.acceleration_z);
    gyroXData.push(data.gyro_x);
    gyroYData.push(data.gyro_y);
    gyroZData.push(data.gyro_z);

    const cutoff = currentTime - 10;
    while (timeData[0] < cutoff) {
      timeData.shift();
      accXData.shift();
      accYData.shift();
      accZData.shift();
      gyroXData.shift();
      gyroYData.shift();
      gyroZData.shift();
    }

    if (accChart && gyroChart) {
      console.log('更新图表:', {timeData, accXData, accYData, accZData, gyroXData, gyroYData, gyroZData});
      accChart.data.labels = timeData;
      accChart.data.datasets[0].data = accXData;
      accChart.data.datasets[1].data = accYData;
      accChart.data.datasets[2].data = accZData;
      gyroChart.data.labels = timeData;
      gyroChart.data.datasets[0].data = gyroXData;
      gyroChart.data.datasets[1].data = gyroYData;
      gyroChart.data.datasets[2].data = gyroZData;
      accChart.update();
      gyroChart.update();
      console.log('图表更新完成');
    }
  } catch (error) {
    console.error('更新可视化出错:', error);
  }
}


// Key press for filter toggle
document.addEventListener('keydown', (event) => {
  if (event.key === ' ') {
    filterEnabled = !filterEnabled;
    console.log(`Filter set to ${filterEnabled ? 'ON' : 'OFF'}`);
  }
});

// Init
function checkChartJsLoaded() {
  if (typeof Chart !== 'undefined') {
    console.log('Chart.js 已加载');
    initCharts();
  } else {
    console.log('Chart.js 未加载，等待...');
    setTimeout(checkChartJsLoaded, 100);
  }
}

init3D();
initAccVector();
checkChartJsLoaded();