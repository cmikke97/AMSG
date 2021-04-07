import os  # Provides a portable way of using operating system dependent functionality

import torch  # Tensor library like NumPy, with strong GPU support
from torch import nn  # a neural networks library deeply integrated with autograd designed for maximum flexibility

import config   # import config.py


class JointEmbeddingNet(nn.Module):
    """
    Joint Embedding Network
    """

    def __init__(self,
                 use_malware=True,  # whether to use the malicious label for the data points or not
                 n_tags=None,  # number of tags to predict
                 feature_dimension=1024,  # dimension of the input data feature vector
                 embedding_dimension=32,  # joint latent space size
                 max_embedding_norm=1,  # value at which to constrain the embedding vector norm to
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

        # create pe embedding head
        self.pe_embedding = nn.Sequential(nn.Linear(layer_sizes[-1], embedding_dimension))

        # create malware/benign labeling head
        self.malware_head = nn.Sequential(nn.Linear(layer_sizes[-1], 1),
                                          # append a Linear Layer with size layer_sizes[-1] x 1
                                          nn.Sigmoid())  # append a sigmoid activation function module

        # create tag embedding
        self.tags_embedding = nn.Embedding(self.n_tags,  # number of lines of the embedding
                                           embedding_dimension,  # dimension of each embedding line
                                           max_norm=max_embedding_norm)  # constrain the embedding vector norm

    def forward(self,
                data,  # current batch of data (features)
                encoded_tags):

        rv = {}  # initialize return value

        # get base result forwarding the data through the base model
        base_out = self.model_base(data)

        if self.use_malware:
            rv['malware'] = self.malware_head(base_out)  # append to return value the result of the malware head

        # get PE embedding
        pe_embedding = self.pe_embedding.forward(base_out)

        # get tags embedding
        tags_embedding = self.tags_embedding(torch.LongTensor(encoded_tags).to(config.device))

        # calculate similarity score between PE and tags embedding
        similarity_score = self.sigmoid(torch.matmul(pe_embedding, tags_embedding.T))

        # save similarity score in result dictionary
        rv['similarity'] = similarity_score

        return rv  # return the return value

    def save(self,
             checkpoint_dir,  # path where to save the model state to
             epoch):  # current epoch

        # save model state of the current epoch to checkpoint dir
        torch.save(self.state_dict(),
                   os.path.join(checkpoint_dir, "epoch_{}.pt".format(str(epoch))))

    def load(self,
             checkpoint_dir,  # path where to retrieve the model state from
             epoch):  # epoch to retrieve the model state of

        # retrieve model state of the specified epoch from checkpoint dir
        self.load_state_dict(torch.load(os.path.join(checkpoint_dir, "epoch_{}.pt".format(str(epoch)))))
