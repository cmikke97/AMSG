# AMSG
Automatic Malware Signature Generation Tool

## Repository file structure
```
root/
|
├── src/        (source files)
|   |
|   ├── DatasetDownloader/        (Dataset Downloader source code)
|   |   |
|   |   ├── sorel20mDownloader.py                 (SOREL 20M dataset downloader python code)
|   |   ├── sorel20mDownloader_Colab.ipynb        (colab (runnable) version of the code)
|   |   └── sorel20mDownloader_Github.ipynb       (colab (runnable) version, it executes "sorel20mDownloader.py")
|   |
|   ├── DetectionBase/        (Train and Evaluate Malware Detection FNN)
|   |   |
|   |   ├── DetectionBase_Colab.ipynb         (colab (runnable) version of the code)
|   |   ├── DetectionBase_Github.ipynb        (colab (runnable) version, it executes "*.py" files)
|   |   ├── config.py                         (configuration file)
|   |   ├── dataset.py                        (dataset loader)
|   |   ├── evaluate.py                       (model evaluation function)
|   |   ├── generators.py                     (generators (Dataloader) definition)
|   |   ├── nets.py                           (FNNs definition)
|   |   ├── plots.py                          (result plotting funcitons)
|   |   └── train.py                          (training function)
|   |
|   └── EmberFeaturesExtractor/       (Ember features extractor (fom PE files) source code)
|       |
|       ├── features.py                 (features extractor python code)
|       ├── features_Colab.ipynb        (colab (runnable) version of the code)
|       └── features_Github.ipynb       (colab (runnable) version, it executes "features.py")
|
└── README.md       (readme (this))
```
