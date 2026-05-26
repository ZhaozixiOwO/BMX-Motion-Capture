import numpy as np

class MadgwickAHRS:
    """
    Madgwick AHRS (Attitude and Heading Reference System) 算法的实现。
    使用加速度计与陀螺仪数据融合估算出设备的方向（四元数）。
    """

    def __init__(self, sample_period=1 / 50, beta=0.1):
        """
        初始化 Madgwick 滤波器参数
        :param sample_period: 采样周期（秒），例如 1/50 表示 50Hz
        :param beta: 算法增益，控制融合强度，数值越大，响应越快但越不稳定
        """
        self.sample_period = sample_period
        self.beta = beta
        self.q = np.array([1.0, 0.0, 0.0, 0.0])  # 初始方向（单位四元数）

    def update(self, gyro, acc):
        """
        更新姿态估计。融合传感器数据。
        :param gyro: 陀螺仪数据 [x, y, z]，单位通常是 rad/s
        :param acc: 加速度计数据 [x, y, z]，单位通常是 g 或 m/s²
        """
        q = self.q
        gyro = np.array(gyro, dtype=float)
        acc = np.array(acc, dtype=float)

        # 步骤 1: 归一化加速度
        norm_acc = np.linalg.norm(acc)
        if norm_acc == 0.0:
            return  # 无效数据，忽略
        acc /= norm_acc

        # 步骤 2: 构建目标函数 f(q) 和 Jacobian 矩阵 J，用于估算姿态偏差
        f = np.array([
            2 * (q[1] * q[3] - q[0] * q[2]) - acc[0],
            2 * (q[0] * q[1] + q[2] * q[3]) - acc[1],
            2 * (0.5 - q[1] ** 2 - q[2] ** 2) - acc[2]
        ])
        j = np.array([
            [-2 * q[2], 2 * q[3], -2 * q[0], 2 * q[1]],
            [2 * q[1], 2 * q[0], 2 * q[3], 2 * q[2]],
            [0, -4 * q[1], -4 * q[2], 0]
        ])

        # 步骤 3: 计算梯度下降方向（用于修正四元数）
        step = j.T.dot(f)
        norm_step = np.linalg.norm(step)
        if norm_step > 1e-8:
            step /= norm_step  # 归一化

        # 步骤 4: 根据陀螺仪积分四元数导数，并加上梯度下降修正项
        q_dot = 0.5 * self.quaternion_multiply(q, np.insert(gyro, 0, 0)) - self.beta * step

        # 步骤 5: 更新当前四元数
        self.q += q_dot * self.sample_period
        self.q /= np.linalg.norm(self.q)  # 归一化保持单位四元数

    @staticmethod
    def quaternion_to_rotation_matrix(q):
        """
        将四元数转换为 3x3 旋转矩阵。
        可用于旋转坐标轴。
        """
        q0, q1, q2, q3 = q
        return np.array([
            [1 - 2 * q2 ** 2 - 2 * q3 ** 2, 2 * q1 * q2 - 2 * q0 * q3, 2 * q1 * q3 + 2 * q0 * q2],
            [2 * q1 * q2 + 2 * q0 * q3, 1 - 2 * q1 ** 2 - 2 * q3 ** 2, 2 * q2 * q3 - 2 * q0 * q1],
            [2 * q1 * q3 - 2 * q0 * q2, 2 * q2 * q3 + 2 * q0 * q1, 1 - 2 * q1 ** 2 - 2 * q2 ** 2]
        ])

    @staticmethod
    def quaternion_to_euler(q):
        """
        将四元数转换为欧拉角（roll, pitch, yaw）
        :return: roll（横滚）, pitch（俯仰）, yaw（偏航），单位为弧度
        """
        q0, q1, q2, q3 = q

        # roll（绕 X 轴旋转）
        sinr_cosp = 2 * (q0 * q1 + q2 * q3)
        cosr_cosp = 1 - 2 * (q1 ** 2 + q2 ** 2)
        roll = np.arctan2(sinr_cosp, cosr_cosp)

        # pitch（绕 Y 轴旋转）
        sinp = 2 * (q0 * q2 - q3 * q1)
        if abs(sinp) >= 1:
            pitch = np.copysign(np.pi / 2, sinp)  # 防止超出范围
        else:
            pitch = np.arcsin(sinp)

        # yaw（绕 Z 轴旋转）
        siny_cosp = 2 * (q0 * q3 + q1 * q2)
        cosy_cosp = 1 - 2 * (q2 ** 2 + q3 ** 2)
        yaw = np.arctan2(siny_cosp, cosy_cosp)

        return roll, pitch, yaw

    @staticmethod
    def quaternion_multiply(q1, q2):
        """
        四元数乘法：用于陀螺仪积分（角速度 → 四元数导数）
        """
        w1, x1, y1, z1 = q1
        w2, x2, y2, z2 = q2
        w = w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2
        x = w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2
        y = w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2
        z = w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2
        return np.array([w, x, y, z])