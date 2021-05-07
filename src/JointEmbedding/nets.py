import os  # Provides a portable way of using operating system dependent functionality

import torch  # Tensor library like NumPy, with strong GPU support
from torch import nn  # a neural networks library deeply integrated with autograd designed for maximum flexibility

import config   # import config.py
from dataset import Dataset  # import Dataset.py

import re
import tempfile
import mlflow
from urllib import parse


class JointEmbeddingNet(nn.Module):
    """
    Joint Embedding Network
    """

    def __init__(self,
                 use_malware=False,  # whether to use the malicious label for the data points or not
                 use_counts=False,  # whether to use the counts for the data points or not
                 n_tags=None,  # number of tags to predict
                 feature_dimension=2381,  # dimension of the input data feature vector
                 embedding_dimension=32,  # joint latent space size
                 max_embedding_norm=1,  # value at which to constrain the embedding vector norm to
                 layer_sizes=None):  # layer sizes (array of sizes)

        # set some attributes
        self.use_malware = use_malware
        self.use_counts = use_counts
        self.n_tags = n_tags

        if self.n_tags is None:  # if we set to use tags but n_tags was None raise an exception
            raise ValueError("n_tags was None but we're trying to predict tags. Please include n_tags")

        # super(PENetwork,self).__init__()
        super().__init__()  # call __init__() method of nn.Module

        # set dropout probability
        p = 0.05

        layers = []  # initialize layers array

        # if layer_sizes was not defined (it is None) then initialize it to a default of [512, 512, 128]
        if layer_sizes is None:
            layer_sizes = [512, 512, 128]

        # for each layer size in layer_sizes
        for i, ls in enumerate(layer_sizes):
            if i == 0:
                # append the first Linear Layer with dimensions feature_dimension x ls
                layers.append(nn.Linear(feature_dimension, ls))
            else:
                # append a Linear Layer with dimensions layer_sizes[i-1] x ls
                layers.append(nn.Linear(layer_sizes[i - 1], ls))

            layers.append(nn.LayerNorm(ls))  # append a Norm layer of size ls
            layers.append(nn.ELU())  # append an ELU activation function module
            layers.append(nn.Dropout(p))  # append a dropout layer with probability of dropout p

        # create a tuple from the layers list, then apply nn.Sequential to get a sequential container
        # -> this will be the model base
        self.model_base = nn.Sequential(*tuple(layers))

        # create pe embedding head
        self.pe_embedding = nn.Sequential(nn.Linear(layer_sizes[-1], embedding_dimension))

        # create malware/benign labeling head
        self.malware_head = nn.Sequential(nn.Linear(layer_sizes[-1], 1),
                                          # append a Linear Layer with size layer_sizes[-1] x 1
                                          nn.Sigmoid())  # append a sigmoid activation function module

        # create count poisson regression head
        self.count_head = nn.Linear(layer_sizes[-1], 1)  # append a Linear Layer with size layer_sizes[-1] x 1

        # sigmoid activation function
        self.sigmoid = nn.Sigmoid()

        # create tag embedding
        self.tags_embedding = nn.Embedding(self.n_tags,  # number of lines of the embedding
                                           embedding_dimension,  # dimension of each embedding line
                                           max_norm=max_embedding_norm)  # constrain the embedding vector norm

    def forward(self,
                data):  # current batch of data (features)

        rv = {}  # initialize return value

        # get base result forwarding the data through the base model
        base_out = self.model_base(data)

        if self.use_malware:
            rv['malware'] = self.malware_head(base_out)  # append to return value the result of the malware head

        if self.use_counts:
            rv['count'] = self.count_head(base_out)  # append to return value the result of the count head

        # get PE embedding
        pe_embedding = self.pe_embedding.forward(base_out)

        # get tags embedding
        tags_embedding = self.tags_embedding(torch.LongTensor(Dataset.encoded_tags).to(config.device))

        # calculate raw logit score between PE and tags embeddings
        raw_logit_score = torch.matmul(pe_embedding, tags_embedding.T)

        # calculate similarity score between PE and tags embedding
        similarity_score = self.sigmoid(raw_logit_score)

        # save raw logit score in result dictionary
        rv['logit_score'] = raw_logit_score

        # save similarity score in result dictionary
        rv['similarity'] = similarity_score

        return rv  # return the return value

    def save(self,
             training_run,  # training run identifier
             epoch):  # current epoch
        """
        Saves model state dictionary to temp directory and then logs it.

        :param training_run: # training run identifier
        :param epoch: Current epoch
        """

        # create temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # compute filename
            filename = os.path.join(temp_dir, "epoch_{}.pt".format(str(epoch)))

            # save model state of the current epoch to temp dir
            torch.save(self.state_dict(), filename)

            # log checkpoint file as artifact
            mlflow.log_artifact(filename, artifact_path=os.path.join("model_checkpoints", str(training_run)))

    def load(self,
             training_run):  # training run identifier
        """
        Loads model checkpoint from current run artifacts, if it exists.
        Returns next epoch number.

        :param training_run: Training run identifier
        """

        # get artifact path from current run
        artifact_path = parse.unquote(parse.urlparse(mlflow.get_artifact_uri()).path)
        # compute checkpoint dir given the current training run identifier
        checkpoint_dir = os.path.join(artifact_path, str(training_run))

        # initialize last epoch done to 0
        last_epoch_done = 0
        # if the checkpoint directory exists
        if os.path.exists(checkpoint_dir):
            # get the latest checkpoint epoch saved in checkpoint dir
            last_epoch_done = self.last_epoch_done(checkpoint_dir)
            # if it is not none, load model state of the specified epoch from checkpoint dir
            if last_epoch_done is not None:
                self.load_state_dict(torch.load(os.path.join(checkpoint_dir, "epoch_{}.pt"
                                                             .format(str(last_epoch_done)))))
            else:
                # otherwise just set last_epoch_done to 0
                last_epoch_done = 0

        # return next epoch to be done
        return last_epoch_done + 1

    @staticmethod
    def last_epoch_done(checkpoint_dir):  # path where to search the model state
        """
        Returns the epoch of the latest checkpoint, if there are checkpoints in the directory provided.
        Otherwise 'None'.

        :param checkpoint_dir: Path where to search the model state
        """

        # set current highest epoch value
        max_epoch = None
        # get highest epoch from the model checkpoints present in the directory
        for epoch in {re.match(r'.*epoch_(\d+).pt', filename).group(1) for filename in os.listdir(checkpoint_dir)}:
            if max_epoch is None or epoch > max_epoch:
                max_epoch = epoch

        # return current highest epoch
        return max_epoch
