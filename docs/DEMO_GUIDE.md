# RouteLLM 双模式课堂 Demo 指南

这份 Demo 用同一个 Streamlit 页面展示两条真实代码路径：

- **Official RouteLLM**：调用官方 `routellm/controller.py::Controller.route` 和官方 `RandomRouter`，展示 routing score、threshold 与 Strong/Weak 模型选择。它不调用付费模型 API。
- **Hierarchical Router**：调用项目现有 `HierarchicalController.decide`、`MultiModelRouter`、`ResourceAwareScheduler` 和 deterministic simulated resource monitor，展示 Top-K、质量约束、资源状态、utility 与最终 `(model, node)`。

展示层没有复制或改写路由公式。三个场景只改变 `NodeState` 输入，最终决策仍由真实 scheduler 计算。

## 1. 如何启动

在 `RouteLLM-hierarchical` 目录运行：

```powershell
& .\run_visual_demo.ps1
```

浏览器通常会自动打开；如果没有，请访问：

```text
http://localhost:8501
```

若当前环境尚未安装 Streamlit：

```powershell
.\setup_windows.ps1
```

无桌面浏览器的验证环境可运行：

```powershell
& .\run_visual_demo.ps1 -Headless
```

脚本启动失败时会打印具体错误；双击运行时默认等待按 Enter，避免窗口闪退。自动化调用可以加 `-NoPause`。

## 2. 课堂推荐演示顺序

### Step 1：Official RouteLLM（30～45 秒）

1. 页面默认在 Hierarchical 模式；课堂开始时先点 **Official RouteLLM**。
2. 选择 Simple 或 Complex preset，也可以直接修改 Query。
3. 保持 threshold 为 `0.60`，点击 **Run Official RouteLLM**。
4. 指出页面中的真实 Router Type、Routing Score、Threshold 和 Strong/Weak 决策。
5. 沿着流程图讲：`Query → Router → Score → Threshold → Strong/Weak`。

建议讲法：

> 可以看到，原始 RouteLLM 解决的是模型选择问题。它根据官方 router score 和阈值，在 strong/weak 两个模型之间选择；决策对象仍然只是 Model。

说明：离线模式使用官方项目内置 `RandomRouter`，因为它是唯一不需要下载 checkpoint 或调用外部 embedding API 的官方 router。它的 score 确实由官方类计算，不是页面硬编码。最终 LLM response 需要外部模型服务，因此课堂离线版在 model selection 处停止。

### Step 2：Hierarchical / Cloud Congestion（1～2 分钟）

1. 切换到 **Hierarchical Router**。
2. 使用默认 Transformer Query。
3. 选择 **Cloud Congestion**，点击 **Run Hierarchical Routing**。
4. 先看紫色 Layer 1：模型按 predicted quality 排序，Top-K 标记清楚。
5. 再看青绿色 Layer 2：Cloud 为 `CONGESTED`，Edge-1 为 `AVAILABLE`。
6. 看橙色 utility 表：选中行是 scheduler 的真实输出。
7. 最后看 **Why not Top-1 Model?**：通常为 `model-b@edge-1` 的 utility 高于 `model-a@cloud`。

建议总结：

> 原始 RouteLLM 回答“选哪个模型”；我们的扩展进一步回答“当前由哪个模型在哪个节点执行更合适”。能力最高的模型不一定是当前最好的执行选择。

### Step 3：切换场景（30～60 秒）

- **Low Load**：Cloud 与 Edge 都没有排队；默认 query 和 seed 下，Top-1 高质量模型会重新成为合理选择。
- **Cloud Congestion**：Cloud 的 GPU 和 queue 很高，第二候选可能在 Edge-1 上获得更高 utility。
- **Edge Congestion**：Edge-1 高负载且可用显存不足，实际 scheduler 会过滤不可运行组合并回到 Cloud。

每次切换场景后点击 **Run Hierarchical Routing**。场景不写死最终答案，只提供资源输入。

## 3. Official RouteLLM 模式重点

- 决策对象：`Model`。
- 输入：Query。
- 核心：官方 router 给出 strong-model win-rate 风格 score，再与 threshold 比较。
- 输出：Strong Model 或 Weak Model。
- 不包含：执行节点、GPU、队列、显存、网络状态。
- 技术追问：展开 **Technical Details**，可展示官方调用路径和真实模型名。

## 4. Hierarchical 模式重点

- 第一层回答：哪些模型有能力完成？
- 第一层使用真实 `predicted_quality` 排序并保留 Top-K。
- 第二层回答：当前由哪个模型在哪个节点执行更合适？
- 第二层先应用 `q_min`，再对可运行的 `(model, node)` 计算 quality、latency、cost、resource load 的联合 utility。
- `actual_quality` 仅用于实验评价；路由只看到带 seed-controlled error 的 `predicted_quality`。
- 若没有可行候选满足 `q_min`，页面显示 **Quality Fallback Triggered**。
- 技术追问：展开 **Technical Details**，可查看 Query Features、actual/predicted quality、归一化量、权重和完整 DecisionRecord。

## 5. 建议总时长

| 环节 | 建议时间 |
|---|---:|
| 开场与问题背景 | 20～30 秒 |
| Official RouteLLM | 30～45 秒 |
| 切换到 Hierarchical | 10 秒 |
| Layer 1 Top-K | 30～45 秒 |
| Layer 2 资源与 Utility | 45～60 秒 |
| Why not Top-1 | 30～45 秒 |
| 场景切换与总结 | 30～60 秒 |

完整 Demo 约 3～5 分钟。

## 6. 现场无网络时如何展示

安装完成后，页面运行不需要网络或付费 API：

- Official 模式使用官方零权重 `RandomRouter`，只复现 model selection。
- Hierarchical 模式使用 deterministic simulation。
- 所有场景、模型 profile、质量估计和 scheduler 都在本地执行。

建议课前：

1. 在有网络环境安装 `requirements-visual-demo.txt`。
2. 运行一次 `run_visual_demo.ps1`，确认浏览器能打开。
3. 保留终端窗口，不要在讲课中途关闭。
4. 准备 README 或本指南作为离线排障资料。

## 7. 常见错误排查

### `Prepared Python environment not found`

当前启动脚本只查找项目根目录的 `.venv\Scripts\python.exe`。如果不存在，请在仓库根目录执行 `.\setup_windows.ps1`。

### `Streamlit is not installed`

执行：

```powershell
.\setup_windows.ps1
```

### 页面没有自动打开

终端出现 `Local URL` 后，手动打开 `http://localhost:8501`。

### 端口 8501 被占用

直接运行：

```powershell
& .\.venv\Scripts\python.exe -m streamlit run .\visual_demo.py --server.port 8502
```

然后访问 `http://localhost:8502`。

### 切换 Query / Scenario 后结果没有变化

修改输入后需要再次点击对应的 **Run** 按钮。页面会提示当前结果仍对应上一次输入。

### Official 模式为什么不显示模型回答

这是明确的离线设计：真实模型调用需要 API key 或本地推理服务。Demo 已真实复现官方 score 与 model selection，并明确显示“final LLM response disabled”。

### 中文或布局显示异常

建议使用 Chrome / Edge 最新版并保持浏览器缩放 90%～100%。1920×1080 投影建议使用浏览器全屏（F11）。
