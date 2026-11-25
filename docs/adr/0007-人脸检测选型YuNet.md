# ADR-0007：人脸检测采用 YuNet，级联分类器保留为降级路径

- 状态：已接受
- 日期：2026 年 11 月 25 日
- 决策人：余青阳、李念
- 相关文档：`docs/adr/0006-隐私打码策略.md`、`docs/10-参考实现调研.md`
- 影响模块：`privacy/detector.py`、配置与模型下载脚本

## 背景

ADR-0006 确定隐私打码采用候选检测加人工复核，其中人脸检测原定使用 OpenCV 自带的级联分类器。该分类器无需额外文件，但基于哈尔特征，在侧脸、遮挡与低照度条件下的漏检率较高，容易把复核负担转嫁给人工。

调研发现，OpenCV 官方模型库提供 YuNet 轻量人脸检测模型。该模型为 MIT 许可证，文件约 227 KB，通过 OpenCV DNN 加载，不引入新的 Python 依赖，并可在中央处理器上实时运行。

## 备选方案

| 方案 | 模型体积 | 依赖 | 准确度 | 跨平台 | 结论 |
|---|---|---|---|---|---|
| OpenCV 级联分类器 | 随库分发 | 无 | 较低，侧脸与遮挡易漏检 | 好 | 保留为降级 |
| YuNet，OpenCV DNN 加载 | 约 227 KB | 无新增，使用 OpenCV DNN | 较高，官方提供 WIDER Face 指标 | 好 | 采用 |
| MediaPipe 人脸检测 | 数 MB | 新增 mediapipe 包 | 较高 | 一般，ARM 与 Windows 的包版本差异较大 | 不采用 |
| RetinaFace 或 YOLO 人脸模型 | 数十 MB | 新增 PyTorch | 高 | 好 | 不采用，超出需求 |
| 云端人脸检测接口 | 无 | 网络与账号 | 高 | 不适用 | 违反离线要求 |

## 决策

1. 人脸候选检测默认使用 YuNet，通过 `cv2.FaceDetectorYN` 加载 ONNX 模型。
2. 模型采用 `face_detection_yunet_2023mar.onnx`，固定输入尺寸，兼容 OpenCV 4.x。
3. 级联分类器保留为降级路径。当模型文件缺失、校验失败或加载异常时，自动切换并在日志中记录。
4. 模型文件不纳入版本控制，由脚本下载并校验 SHA-256。下载地址与校验值写入脚本常量。
5. 检测结果仅作为候选区域，仍须人工复核，与 ADR-0006 的流程一致。

## 理由

1. 模型体积约 227 KB，对镜像体积与仓库体积的影响可忽略。
2. 使用 OpenCV DNN 加载，不新增依赖，双架构容器方案不受影响。
3. 精度优于哈尔特征分类器，可减少人工补框的工作量。
4. 模型为 MIT 许可证，允许在课程项目中自由使用，只须保留版权声明。
5. 固定输入版本兼容当前 OpenCV 4.x 环境，避免动态维度在旧版本上的兼容问题。

## 后果

1. 环境初始化增加一步模型下载，失败时降级为级联分类器，不阻断流程。
2. 配置新增检测器选项，默认值为 `yunet`，可选 `haar`。
3. 报告中须声明所用模型及许可证。
4. 若后续升级至 OpenCV 5.x，可改用动态输入版本，接口不变。
5. 该变更不影响二维码检测。二维码首版仍使用 OpenCV 内置检测器，`zxing-cpp` 作为备选。

## 参考

1. https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet
2. https://github.com/ShiqiYu/libfacedetection.train
3. https://docs.opencv.org/4.x/df/d20/classcv_1_1FaceDetectorYN.html
