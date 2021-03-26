# 评估

#### eval\_config

```sql
eval_config {
  metrics_set: {
    # metric为auc
    auc {}
  }
}
```

- metrics\_set: 配置评估指标，可以配置多个，如:

```sql
eval_config {
  metrics_set: {
    # metric为auc
    auc {}
    # metric为mae
    mean_absolute_error {}
  }
}
```

- num\_examples: 默认为0, 表示评估所有样本；大于0，则每次只评估num\_examples样本，一般在调试或者示例的时候使用

#### Metric:

| AUC               | auc {}                   | CTR模型LossType=CLASSIFICATION, num\_class=1   |
| ----------------- | ------------------------ | -------------------------------------------- |
| Accuracy          | accuracy {}              | 多分类模型LossType=CLASSIFICATION, num\_class > 1 |
| MeanAbsoluteError | mean\_absolute\_error {} | 回归模型LossType=L2\_LOSS                        |
| RecallAtTopK      | recall\_at\_topk {}      | 多分类模型LossType=CLASSIFICATION, num\_class > 1 |

#### 评估命令

```sql
pai -name easy_rec_ext -project algo_public
-Dconfig=oss://easyrec/easy_rec_test/dwd_avazu_ctr_deepmodel_ext.config
-Dcmd=evaluate
-Dtables=odps://pai_online_project/tables/dwd_avazu_ctr_deepmodel_test
-Dcluster='{"worker" : {"count":1, "cpu":1000, "gpu":100, "memory":40000}}'
-Darn=acs:ram::xxx:role/ev-ext-test-oss
-Dbuckets=oss://easyrec/
-DossHost=oss-cn-shanghai-internal.aliyuncs.com；
```

- \-Dconfig: 同训练
- \-Dcmd: evaluate 模型评估
- \-Dtables: 只需要指定测试 tables
- \-Dcheckpoint\_path: 使用指定的checkpoint\_path，默认不填
