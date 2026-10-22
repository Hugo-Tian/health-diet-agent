# GitHub调研与实现取舍

查阅日期2026-10-21。仅借鉴方法，未复制外部仓库代码、安装整个外部项目或导入其医学语料。

| 项目 | 方法 | 本项目采用 |
|---|---|---|
| [LangChain RAG From Scratch](https://github.com/langchain-ai/rag-from-scratch) | 索引、查询转换、检索与生成分层 | 数据、检索、生成分开；整理问法辅助检索 |
| [LangChain EnsembleRetriever](https://github.com/langchain-ai/langchain/blob/master/libs/langchain/langchain_classic/retrievers/ensemble.py) | Reciprocal Rank Fusion | 独立实现RRF，按名次融合不同排序 |
| [MedRAG](https://github.com/gzxiong/MedRAG) | 多来源医学分片，BM25和语义检索对照 | 保存片段来源、范围、版本；加入BM25 |
| [Ragas](https://github.com/vibrantlabsai/ragas) | 以测试集和指标评估RAG | 确定性回归集、Recall@6、负例拒绝率；未安装Ragas或使用LLM裁判 |

MedRAG的MedCorp包括PubMed、StatPearls、教材、Wikipedia，体量大且用途混合；仓库代码许可不自动授予底层语料再发布权限。因此没有全量下载或重分发。实际知识采用NIDDK/NHLBI官方患者教育页的短摘录、中文概述和原文链接。

新增原文：[腹泻](https://www.niddk.nih.gov/health-information/digestive-diseases/diarrhea/eating-diet-nutrition)、[肠易激](https://www.niddk.nih.gov/health-information/digestive-diseases/irritable-bowel-syndrome/eating-diet-nutrition)、[胃炎](https://www.niddk.nih.gov/health-information/digestive-diseases/gastritis-gastropathy/eating-diet-nutrition)、[DASH](https://www.nhlbi.nih.gov/health/dash-eating-plan)。

16片段规模下采用BM25与整理问法匹配便于本地部署，无新增API密钥或大模型下载。没有做语义向量对照，不宣称优于向量检索；后续扩库可加入中文Embedding、重排和独立留出集。代码见backend/app/retrieval.py与backend/app/evaluate_rag.py。
