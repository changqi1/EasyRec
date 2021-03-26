# 导出

#### export\_config

```protobuf
export_config {
}
```

- batch\_size: 导出模型的batch\_size，默认是-1，即可以接收任意batch\_size
- exporter\_type: 导出类型,  best | final | latest | none
  - best是指导出最好的模型
  - final是只是再训练结束导出
  - latest导出最新的模型
  - none 不导出
- dump\_embedding\_shape: 打印出embedding的shape，方便在EAS上部署分片大模型
- best\_exporter\_metric: 当exporter\_type为best的时候，确定最优导出模型的metric，注意该metric要在eval\_config的metrics\_set设置了才行
- metric\_bigger: 确定最优导出模型的metric是越大越好，还是越小越好，默认是越大越好
- exports\_to\_keep: only keep n best or latest models, only for exporter\_type in \[best, lastest\], default to 1
- multi\_placeholder: use multiple placeholders or a single placeholder
  - Default to true, that is to use one placeholder for each feature.
  - If a single placeholder is used, the placeholder is named "feature", and its signature is also named "feature".
  - If multiple placeholder is used, each placeholder is named "input\_{id}", where {id} indicates **the order** in data\_config.input\_fields.input\_name, and its signature is input\_name defined in data\_config.input\_fields.input\_name.
- multi\_value\_fields: a list specify the fields input as an dense array, only used for tag features, this could save the time of string split, and convert string to int or float time.
  ```protobuf
  export_config {
    multi_value_fields {
       input_name: ["field1", "field2", "field3"]
    }
  }
  ```
- placeholder\_named\_by\_input: name each placeholder by input\_name instead of **the order** of input\_name in data\_config.input\_fields.input\_name.

#### 导出命令

PAI

```sql
pai -name easy_rec_ext -project algo_public
-Dconfig=oss://easyrec/easy_rec_test/dwd_avazu_ctr_deepmodel_ext.config
-Dcmd=export
-Dexport_dir=oss://easyrec/easy_rec_test/export
-Dcluster='{"worker" : {"count":1, "cpu":1000, "memory":40000}}'
-Darn=acs:ram::xxx:role/ev-ext-test-oss
-Dbuckets=oss://easyrec/
-DossHost=oss-cn-shanghai-internal.aliyuncs.com
```

- \-Dconfig: 同训练
- \-Dcmd: export 模型导出
- \-Dexport\_dir: 导出的目录
- \-Dcheckpoint\_path: 使用指定的checkpoint\_path
