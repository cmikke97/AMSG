import os  # Provides a portable way of using operating system dependent functionality

import torch  # Tensor library like NumPy, with strong GPU support
from torch import nn  # a neural networks library deeply integrated with autograd designed for maximum flexibility


class PENetwork(nn.Module):
    """
    This is a simple network loosely based on the one used in ALOHA: Auxiliary Loss Optimization for
    Hypothesis Augmentation (https://arxiv.org/abs/1903.05700)
    Note that it uses fewer (and smaller) layers, as well as a single layer for all tag predictions,
    performance will suffer accordingly.
    """

    def __init__(self,
                 use_malware=True,  # whether to use the malicious label for the data points or not
                 use_counts=True,  # whether to use the counts for the data points or not
                 use_tags=True,  # whether to use the tags for the data points or not
                 n_tags=None,  # number of tags to predict
                 feature_dimension=1024,  # dimension of the input data feature vector
                 layer_sizes=None):  # layer sizes (array of sizes)

        # set some attributes
        self.use_malware = use_malware
        self.use_counts = use_counts
        self.use_tags = use_tags
        self.n_tags = n_tags

        if self.use_tags and self.n_tags is None:  # if we set to use tags but n_tags was None raise an exception
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

        # create a tuple from the layers list, then apply nn.Sequential to get a sequential container
        # -> this will be the model base
        self.model_base = nn.Sequential(*tuple(layers))

        # create malware/benign labeling head
        self.malware_head = nn.Sequential(nn.Linear(layer_sizes[-1], 1),
                                          # append a Linear Layer with size layer_sizes[-1] x 1
                                          nn.Sigmoid())  # append a sigmoid activation function module

        # create count poisson regression head
        self.count_head = nn.Linear(layer_sizes[-1], 1)  # append a Linear Layer with size layer_sizes[-1] x 1

        # sigmoid activation function
        self.sigmoid = nn.Sigmoid()

        # create a tag multi-label classifying head
        self.tag_head = nn.Sequential(nn.Linear(layer_sizes[-1], 64),
                                      # append a Linear Layer with size layer_sizes[-1] x 64
                                      nn.ELU(),  # append an ELU activation function module
                                      nn.Linear(64, 64),  # append a Linear Layer with size 64 x 64
                                      nn.ELU(),  # append an ELU activation function module
                                      nn.Linear(64, n_tags),  # append a Linear Layer with size 64 x n_tags
                                      nn.Sigmoid())  # append a sigmoid activation function module

    def forward(self,
                data):  # current batch of data (features)

        rv = {}  # initialize return value

        base_result = self.model_base.forward(data)  # get base result forwarding the data through the base model

        if self.use_malware:
            rv['malware'] = self.malware_head(base_result)  # append to return value the result of the malware head

        if self.use_counts:
            rv['count'] = self.count_head(base_result)  # append to return value the result of the count head

        if self.use_tags:
            rv['tags'] = self.tag_head(base_result)  # append to return value the result of the tag head

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
