# AMSG
Automatic Malware Signature Generation Tool

# Wiki
There is now a wiki!

# Repository file structure
<pre>
<a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation' title='repository root'>root/</a>
|
├── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/tree/main/src' title='source files'>src/</a> - - - - - - - - - - - - - - - - - - - (source files)
|   |
|   ├── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/tree/main/src/DatasetDownloader' title='DatasetDownloader folder'>DatasetDownloader/</a> - - - - - - - - - - - - (Dataset Downloader source code <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki/DatasetDownloader' title='DatasetDownloader wiki page'>📖Wiki</a>)
|   |   |
|   |   ├── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/blob/main/src/DatasetDownloader/DatasetDownloader.ipynb' title='DatasetDownloader notebook'>DatasetDownloader.ipynb</a>  - - - - - - - - - (notebook (runnable) <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki/DatasetDownloader.ipynb' title='sorel20mDownloader notebook wiki page'>📖Wiki</a>)
|   |   └── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/blob/main/src/DatasetDownloader/sorel20mDownloader.py' title='sorel20mDownloader code'>sorel20mDownloader.py</a>  - - - - - - - - - - (SOREL 20M dataset downloader python code <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki/sorel20mDownloader.py' title='sorel20mDownloader wiki page'>📖Wiki</a>)
|   |
|   ├── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/tree/main/src/DetectionBase' title='DetectionBase folder'>DetectionBase/</a> - - - - - - - - - - - - - - (Train and Evaluate Malware Detection FNN <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki/DetectionBase' title='DetectionBase wiki page'>📖Wiki</a>)
|   |   |
|   |   ├── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/blob/main/src/DetectionBase/DetectionBase.ipynb' title='DetectionBase notebook'>DetectionBase.ipynb</a>  - - - - - - - - - - - (notebook (runnable) <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki/DetectionBase.ipynb' title='DetectionBase notebook wiki page'>📖Wiki</a>)
|   |   ├── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/blob/main/src/DetectionBase/config.py' title='config'>config.py</a>  - - - - - - - - - - - - - - - - (configuration file <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki/DetectionBase_config.py' title='DB config wiki page'>📖Wiki</a>)
|   |   ├── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/blob/main/src/DetectionBase/dataset.py' title='dataset module'>dataset.py</a> - - - - - - - - - - - - - - - - (dataset loader <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki/DetectionBase_dataset.py' title='DB dataset wiki page'>📖Wiki</a>)
|   |   ├── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/blob/main/src/DetectionBase/evaluate.py' title='evaluate module'>evaluate.py</a>  - - - - - - - - - - - - - - - (model evaluation function <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki/DetectionBase_evaluate.py' title='DB evaluate wiki page'>📖Wiki</a>)
|   |   ├── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/blob/main/src/DetectionBase/generators.py' title='generators module'>generators.py</a>  - - - - - - - - - - - - - - (generators (Dataloader) definition <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki/DetectionBase_generators.py' title='DB evaluate wiki page'>📖Wiki</a>)
|   |   ├── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/blob/main/src/DetectionBase/nets.py' title='nets module'>nets.py</a>  - - - - - - - - - - - - - - - - - (FNNs definition <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki/DetectionBase_nets.py' title='DB evaluate wiki page'>📖Wiki</a>)
|   |   ├── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/blob/main/src/DetectionBase/plots.py' title='plots module'>plots.py</a> - - - - - - - - - - - - - - - - - (result plotting functions <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki/DetectionBase_plots.py' title='DB plots wiki page'>📖Wiki</a>)
|   |   └── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/blob/main/src/DetectionBase/train.py' title='train module'>train.py</a> - - - - - - - - - - - - - - - - - (training function <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki/DetectionBase_train.py' title='DB plots wiki page'>📖Wiki</a>)
|   |
|   ├── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/tree/main/src/EmberFeaturesExtractor' title='EmberFeaturesExtractor folder'>EmberFeaturesExtractor/</a>  - - - - - - - - - (Ember features extractor (fom PE files) source code <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki/EmberFeaturesExtractor' title='DB plots wiki page'>📖Wiki</a>)
|   |   |
|   |   ├── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/blob/main/src/EmberFeaturesExtractor/features.py' title='features code'>features.py</a>  - - - - - - - - - - - - - - - (features extractor python code <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki/features.py' title='DB plots wiki page'>📖Wiki</a>)
|   |   └── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/blob/main/src/EmberFeaturesExtractor/EmberFeaturesExtractor.ipynb' title='EmberFeaturesExtractor notebook'>EmberFeaturesExtractor.ipynb</a> - - - - - - - (notebook (runnable) <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki/EmberFeaturesExtractor.ipynb' title='DB plots wiki page'>📖Wiki</a>)
|   |
|   └── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/tree/main/src/JointEmbedding' title='JointEmbedding folder'>JointEmbedding/</a>  - - - - - - - - - - - - - (Train and Evaluate Joint Embedding FNN <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki/JointEmbedding' title='DB plots wiki page'>📖Wiki</a>)
|       |
|       ├── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/blob/main/src/JointEmbedding/JointEmbedding.ipynb' title='JointEmbedding notebook'>JointEmbedding.ipynb</a> - - - - - - - - - - - (notebook (runnable) <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki/JointEmbedding.ipynb' title='DB plots wiki page'>📖Wiki</a>)
|       ├── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/blob/main/src/JointEmbedding/config.py' title='config'>config.py</a>  - - - - - - - - - - - - - - - - (configuration file <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki/JointEmbedding_config.py' title='DB plots wiki page'>📖Wiki</a>)
|       ├── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/blob/main/src/JointEmbedding/dataset.py' title='dataset module'>dataset.py</a> - - - - - - - - - - - - - - - - (dataset loader <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki/JointEmbedding_dataset.py' title='DB plots wiki page'>📖Wiki</a>)
|       ├── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/blob/main/src/JointEmbedding/evaluate.py' title='evaluate module'>evaluate.py</a>  - - - - - - - - - - - - - - - (model evaluation function <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki/JointEmbedding_evaluate.py' title='DB plots wiki page'>📖Wiki</a>)
|       ├── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/blob/main/src/JointEmbedding/generators.py' title='generators module'>generators.py</a>  - - - - - - - - - - - - - - (generators (Dataloader) definition <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki/JointEmbedding_generators.py' title='DB plots wiki page'>📖Wiki</a>)
|       ├── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/blob/main/src/JointEmbedding/nets.py' title='nets module'>nets.py</a>  - - - - - - - - - - - - - - - - - (FNNs definition <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki/JointEmbedding_nets.py' title='DB plots wiki page'>📖Wiki</a>)
|       ├── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/blob/main/src/JointEmbedding/plots.py' title='plots module'>plots.py</a> - - - - - - - - - - - - - - - - - (result plotting functions<a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki/JointEmbedding_plots.py' title='DB plots wiki page'>📖Wiki</a>)
|       └── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/blob/main/src/JointEmbedding/train.py' title='train module'>train.py</a> - - - - - - - - - - - - - - - - - (training function <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki/JointEmbedding_train.py' title='DB plots wiki page'>📖Wiki</a>)
|
└── <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/blob/main/README.md' title='README'>README.md</a>  - - - - - - - - - - - - - - - - (README)
</pre>
