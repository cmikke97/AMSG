import torch
from torch import nn  # a neural networks library deeply integrated with autograd designed for maximum flexibility
import config

from logzero import logger  # Robust and effective logging for Python


class JointEmbeddingNet(nn.Module):
    """
    Joint Embedding Network
    """

    def __init__(self,
                 use_malware=True,  # whether to use the malicious label for the data points or not
                 n_tags=None,  # number of tags to predict
                 feature_dimension=1024,  # dimension of the input data feature vector
                 layer_sizes=None):  # layer sizes (array of sizes)

        # set some attributes
        self.use_malware = use_malware
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
                layers.append(nn.Linear(feature_dimension,
                                        ls))  # append the first Linear Layer with dimensions feature_dimension x ls
            else:
                layers.append(
                    nn.Linear(layer_sizes[i - 1], ls))  # append a Linear Layer with dimensions layer_sizes[i-1] x ls

            layers.append(nn.LayerNorm(ls))  # append a Norm layer of size ls
            layers.append(nn.ELU())  # append an ELU activation function module
            layers.append(nn.Dropout(p))  # append a dropout layer with probability of dropout p

        self.sigmoid = nn.Sigmoid()

        # create a tuple from the layers list, then apply nn.Sequential to get a sequential container
        # -> this will be the model base
        self.model_base = nn.Sequential(*tuple(layers))

        self.pe_embedding = nn.Sequential(nn.Linear(layer_sizes[-1], n_tags))

        # create malware/benign labeling head
        self.malware_head = nn.Sequential(nn.Linear(layer_sizes[-1], 1),
                                          # append a Linear Layer with size layer_sizes[-1] x 1
                                          nn.Sigmoid())  # append a sigmoid activation function module

        self.tags_embedding = nn.Embedding(self.n_tags, self.n_tags)

    def forward(self,
                data,   # current batch of data (features)
                encoded_tags):

        rv = {}  # initialize return value

        # get base result forwarding the data through the base model
        base_out = self.model_base(data)

        if self.use_malware:
            rv['malware'] = self.malware_head(base_out)  # append to return value the result of the malware head

        # get PE embedding
        pe_embedding = self.pe_embedding.forward(base_out)

        logger.info("pe_embedding:")
        logger.info(pe_embedding)
        logger.info(pe_embedding.shape)

        # get tags embedding
        tags_embedding = self.tags_embedding(torch.LongTensor(encoded_tags).to(config.device))

        logger.info("tags_embedding:")
        logger.info(tags_embedding)
        logger.info(tags_embedding.shape)

        # calculate similarity score between PE and tags embedding
        similarity_score = self.sigmoid(torch.matmul(tags_embedding, pe_embedding))

        logger.info("similarity_score:")
        logger.info(similarity_score)
        logger.info(similarity_score.shape)

        rv['similarity'] = similarity_score

        return rv  # return the return value
