# AMSG
Automatic Malware Signature Generation Tool

## Repository file structure
<pre>
root/
|
├── src/        (source files)
|   |
|   ├── DatasetDownloader/        (Dataset Downloader source code)
|   |   |
|   |   ├── sorel20mDownloader.py                 (SOREL 20M dataset downloader python code)
|   |   └── sorel20mDownloader_Github.ipynb       (colab (runnable))
|   |
|   ├── DetectionBase/        (Train and Evaluate Malware Detection FNN)
|   |   |
|   |   ├── DetectionBase_Github.ipynb        (colab (runnable))
|   |   ├── config.py                         (configuration file)
|   |   ├── dataset.py                        (dataset loader)
|   |   ├── evaluate.py                       (model evaluation function)
|   |   ├── generators.py                     (generators (Dataloader) definition)
|   |   ├── nets.py                           (FNNs definition)
|   |   ├── plots.py                          (result plotting funcitons)
|   |   └── train.py                          (training function)
|   |
|   ├── EmberFeaturesExtractor/       (Ember features extractor (fom PE files) source code)
|   |   |
|   |   ├── features.py                 (features extractor python code)
|   |   ├── features_Colab.ipynb        (colab (runnable) version of the code)
|   |   └── features_Github.ipynb       (colab (runnable) version, it executes "features.py")
|   |
|   └── JointEmbedding/             (Train and Evaluate Joint Embedding FNN)
|       |
|       ├── JointEmbedding_Github.ipynb       (colab (runnable))
|       ├── config.py                         (configuration file)
|       ├── dataset.py                        (dataset loader)
|       ├── evaluate.py                       (model evaluation function)
|       ├── generators.py                     (generators (Dataloader) definition)
|       ├── nets.py                           (FNNs definition)
|       ├── plots.py                          (result plotting funcitons)
|       └── train.py                          (training function)
|
└── README.md       (readme (this))
</pre>
