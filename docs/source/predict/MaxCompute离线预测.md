# MaxCompute离线预测

### 前置条件：

- 模型训练
- 模型导出

### 离线预测

```bash
drop table if exists ctr_test_output;
pai -name easy_rec_ext
-Dcmd=predict
-Dcluster='{"worker" : {"count":5, "cpu":1600,  "memory":40000, "gpu":100}}'
-Darn=acs:ram::1217060697188167:role/ev-ext-test-oss
-Dbuckets=oss://easyrec/
-Dsaved_model_dir=oss://easyrec/easy_rec_test/experiment/ctr_export/1597299619
-Dinput_table=odps://pai_online_project/tables/test_longonehot_4deepfm_20
-Doutput_table=odps://pai_online_project/tables/ctr_test_output
-Dexcluded_cols=label
-Dreserved_cols=ALL_COLUMNS
-Dbatch_size=1024
-DossHost=oss-cn-shanghai-internal.aliyuncs.com;
```

- save\_modeld\_dir: 导出的模型目录
- output\_table: 输出表，不需要提前创建，会自动创建
- excluded\_cols: 预测模型不需要的columns，比如labels
- selected\_cols: 预测模型需要的columns，selected\_cols和excluded\_cols不能同时使用
- reserved\_cols: 需要copy到output\_table的columns, 和excluded\_cols/selected\_cols不冲突，如果指定ALL\_COLUMNS，则所有的column都被copy到output\_table
- batch\_size: minibatch的大小
- ossHost: oss bucket的host
- output\_cols: output\_name和类型, 如:
  - \-Doutput\_cols="probs double"
  - 如果有多列，用逗号分割, -Doutput\_cols='probs double, embedding string'
- model\_outputs: 导出saved\_model时模型的导出字段，可以不指定，默认和output\_cols一致
  - 如果output\_cols和model\_outputs不一致时需要指定，如:
  ```sql
  -Doutput_cols='score double' -Dmodel_outputs='probs'
  ```
  - 如果有多列，用逗号分割
  ```sql
  -Doutput_cols='scores double, v string'
  -Dmodel_outputs='probs,embedding'
  ```
  - ctr模型(num\_class=1)，导出字段:logits、probs，对应: sigmoid之前的值/概率
  - 回归模型，导出字段: y，对应: 预测值
  - 多分类模型，导出字段: logits/probs/y，对应: softmax之前的值/概率/类别id
- lifecyle: output\_table的lifecyle

### 输出表schema:

包含reserved\_cols和output\_cols
