# EasyRec简介

## What is&#160;EasyRec?

![intro.png](../images/intro.png)

### EasyRec is an easy to use framework for Recommendation

EasyRec implements state of the art machine learning models used in common recommedation tasks: candidate generation(matching), scoring(ranking), and multi-task learning. It improves the efficiency of generating high performance models by simple configuration and hyper parameter tuning(HPO).

## Why EasyRec?

### Run everywhere

- Local / [MaxCompute](https://help.aliyun.com/product/27797.html) / [DataScience](https://help.aliyun.com/document_detail/170836.html) / [DLC](https://www.alibabacloud.com/help/zh/doc-detail/165137.htm?spm=a2c63.p38356.b99.79.4c0734a4bVav8D)
- TF1.12-1.15 / TF2.x / PAI-TF

### Diversified input data

- [MaxCompute Table](https://help.aliyun.com/document_detail/27819.html?spm=a2c4g.11186623.6.554.91d517bazK7nTF)
- HDFS files
- [OSS files](https://help.aliyun.com/product/31815.html?spm=5176.7933691.1309819.8.5bb52a66ZQOobj)
- Kafka Streams
- Local CSV

### Simple to config

- Flexible feature config and simple model config
- Efficient and robust feature generation\[used in taobao\]
- Nice web interface in development

### It is smart

- EarlyStop / Best Checkpoint Saver
- [Hyper Parameter Search](automl/hpo_pai.md) / [AutoFeatureCross](automl/auto_cross_emr.md)
- In development: NAS, Knowledge Distillation

### Large scale and easy deployment

- Support large scale embedding, incremental saving
- Many parallel strategies: ParameterServer, Mirrored, MultiWorker
- Easy deployment to [EAS](https://help.aliyun.com/document_detail/113696.html?spm=a2c4g.11174283.6.745.344d1987M3j15E): automatic scaling, easy monitoring
- Consistency guarantee: train and serving

### A variety of models

- [DeepFM](models/deepfm.md) / [MultiTower](models/multi_tower.md) / [Deep Interest Network](models/din.md) / [DSSM](models/dssm.md) / [MMoE](models/mmoe.md) / [ESMM](models/esmm.md)
- More models in development

### Easy to customize

- Easy to implement [customized models](models/user_define.md)
- Not need to care about data pipelines
