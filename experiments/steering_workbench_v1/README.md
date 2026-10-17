# Steering Workbench v1

自包含 HTML 工作台：把 readout atlas、construction、transfer、sweep、recipe 与
intervention algorithm guide 串成一条从 hidden states 到可执行向量的设计链。

- 文件：steering_workbench.html
- 网页副本：frontend/public/steering-workbench.html（URL /steering-workbench.html）
- 生成器：backend/examples/build_steering_workbench.py
- 预览：preview.png（Quick Look 缩略图，只覆盖 overview tab）
- 测试：backend/tests/test_steering_workbench.py

页面不重跑模型；所有数字来自 experiments/* 产物。打开方式：直接用浏览器打开
steering_workbench.html，或启动 Next 后访问 /steering-workbench.html。

## Tab

Overview / Readout / Construction / Transfer / Dose / Recipe / Algorithm guide / Design guide。

## 重新生成

    python3 backend/examples/build_steering_workbench.py
    python3 -m pytest backend/tests/test_steering_workbench.py -q
