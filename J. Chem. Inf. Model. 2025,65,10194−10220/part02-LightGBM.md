
### 1.LightGBM 模型构建与训练
这部分说明了 LightGBM 的具体参数设置和训练测试集划分。

*   **英文摘录：** "The LGBMClassifier from the lightgbm library was initialized with 100 estimators and default hyperparameters... The same 80:20 training−validation split and random seed (random_state = 42) were applied for consistency."
*   **中文翻译：** 使用 lightgbm 库中的 LGBMClassifier，初始化时设置 **100 个估计器 (estimators)** 并使用默认超参数……为了保持一致性，应用了相同的 **80:20 训练-验证划分**和随机种子 (random_state = 42)。

### **4. 验证策略 (Validation Strategy)**
文章采用了固定划分和 5 折交叉验证两种方式。

*   **英文摘录：** "Model validation was performed on the full original training data set using both a fixed training/test split and stratified 5-fold cross-validation (5-fold CV)... First, a single stratified hold-out split was applied... with 80% used for training and 20% for test.",
*   **中文翻译：** 在完整的原始训练数据集上，同时使用**固定训练/测试划分**和**分层 5 折交叉验证 (5-fold CV)** 进行模型验证……首先，应用了单次分层留出划分……其中 80% 用于训练，20% 用于测试。,

### **5. 性能评估指标 (Performance Metrics)**
文章定义了您提到的所有核心评估指标。

*   **英文摘录：** "Accuracy (eq 1)... Matthews correlation coefficient (MCC) (eq 2)... sensitivity (eq 3)... specificity (eq 4)... area under the receiver operating characteristic curve (AUROC)... effectively summarizing the trade-off between sensitivity and 1-specificity.",
*   **中文翻译：** **准确率 (Accuracy)**（公式 1）……**马修斯相关系数 (MCC)**（公式 2）……**灵敏度 (Sensitivity)**（公式 3）……**特异度 (Specificity)**（公式 4）……**受试者工作特征曲线下面积 (AUROC)**……有效总结了灵敏度与 1-特异度之间的权衡。,
    *   *注：来源中也提到了混淆矩阵 (Confusion Matrix) 用于记录真阳性 (TP)、真阴性 (TN) 等数值,。*

