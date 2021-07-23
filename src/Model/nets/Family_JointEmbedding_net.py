import configparser  # implements a basic configuration language for Python programs
import os  # provides a portable way of using operating system dependent functionality
from copy import deepcopy  # creates a new object and recursively copies the original object elements

import numpy as np
import torch  # tensor library like NumPy, with strong GPU support
import torch.nn.functional as F  # pytorch neural network functional interface
from torch import nn  # a neural networks library deeply integrated with autograd designed for maximum flexibility

from .utils.Net import Net as baseNet

# get config file path
nets_dir = os.path.dirname(os.path.abspath(__file__))
model_dir = os.path.dirname(nets_dir)
src_dir = os.path.dirname(model_dir)
config_filepath = os.path.join(src_dir, 'config.ini')

# instantiate config parser and read config file
config = configparser.ConfigParser()
config.read(config_filepath)

# get variables from config file
device = config['jointEmbedding']['device']


class Net(baseNet):
    """ Joint Embedding Network which calculated embeddings similarity using the dot product. """

    def __init__(self,
                 families,  # list of families to predict
                 feature_dimension=2381,  # dimension of the input data feature vector
                 embedding_dimension=32,  # joint latent space size
                 max_embedding_norm=1,  # value at which to constrain the embedding vector norm to
                 layer_sizes=None,  # layer sizes (array of sizes)
                 dropout_p=0.05,  # dropout probability
                 activation_function='elu'):  # non-linear activation function to use
        """ Initialize net.

        Args:
            families: List of families to predict
            feature_dimension: Dimension of the input data feature vector
            embedding_dimension: Joint latent space size
            max_embedding_norm: Value at which to constrain the embedding vector norm to
            layer_sizes: Layer sizes (array of sizes)
            dropout_p: Dropout probability
            activation_function: Non-linear activation function to use
        """

        self.families = families
        self.n_families = len(families)
        self.encoded_families = [idx for idx in range(self.n_families)]
        self.embedding_dimension = embedding_dimension

        # initialize super class
        super().__init__()

        layers = []  # initialize layers array

        # if layer_sizes was not defined (it is None) then initialize it to a default of [512, 512, 128]
        if layer_sizes is None:
            layer_sizes = [512, 512, 128]

        # select activation function to use based on the activation_function parameter
        if activation_function.lower() == 'elu':
            self.activation_function = nn.ELU
        elif activation_function.lower() == 'leakyrelu':
            self.activation_function = nn.LeakyReLU
        elif activation_function.lower() == 'prelu':
            self.activation_function = nn.PReLU
        elif activation_function.lower() == 'relu':
            self.activation_function = nn.ReLU
        else:  # if the provided function is not recognised, raise error
            raise ValueError('Unknown activation function {}. Try "elu", "leakyRelu", "pRelu" or "relu"'
                             .format(activation_function))

        # for each layer size in layer_sizes
        for i, ls in enumerate(layer_sizes):
            if i == 0:
                # append the first Linear Layer with dimensions feature_dimension x ls
                layers.append(nn.Linear(feature_dimension, ls))
            else:
                # append a Linear Layer with dimensions layer_sizes[i-1] x ls
                layers.append(nn.Linear(layer_sizes[i - 1], ls))

            layers.append(nn.LayerNorm(ls))  # append a Norm layer of size ls
            layers.append(self.activation_function())  # append an ELU activation function module
            layers.append(nn.Dropout(dropout_p))  # append a dropout layer with probability of dropout dropout_p

        # create a tuple from the layers list, then apply nn.Sequential to get a sequential container
        # -> this will be the model base
        self.model_base = nn.Sequential(*tuple(layers))

        # create pe embedding head
        self.pe_embedding = nn.Sequential(nn.Linear(layer_sizes[-1], self.embedding_dimension))

        # sigmoid activation function
        self.sigmoid = nn.Sigmoid()

        # create tag embedding
        self.families_embedding = nn.Embedding(self.n_families,  # number of lines of the embedding
                                               self.embedding_dimension,  # dimension of each embedding line
                                               max_norm=max_embedding_norm)  # constrain the embedding vector norm

    def forward(self,
                data):  # current batch of data (features)
        """ Forward batch of data through the net.

        Args:
            data: Current batch of data (features)
        Returns:
            Dictionary containing predicted family labels.
        """

        rv = {}  # initialize return value

        # get base result forwarding the data through the base model
        base_out = self.model_base(data)

        # get PE embedding
        pe_embedding = self.pe_embedding.forward(base_out)

        # get tags embedding
        families_embedding = self.families_embedding(torch.LongTensor(self.encoded_families).to(device))

        # calculate similarity score between PE and families embeddings using dot product
        similarity_scores = torch.matmul(pe_embedding, families_embedding.T)

        # calculate probability score (estimated probability that 'x' is of family 'f')
        # between PE and family embedding
        probability_scores = self.sigmoid(similarity_scores)

        # save similarity score in result dictionary
        rv['similarity'] = similarity_scores

        # save probability score in result dictionary
        rv['probability'] = probability_scores

        return rv  # return return value

    def get_embedding(self,
                      data):  # current batch of data (features)
        """ Forward batch of data through the net and get resulting embedding.

        Args:
            data: Current batch of data (features)
        Returns:
            Dictionary containing the resulting embedding.
        """

        rv = {}  # initialize return value

        # get base result forwarding the data through the base model
        base_out = self.model_base(data)

        # get PE embedding
        pe_embedding = self.pe_embedding.forward(base_out)

        # save embedding score in result dictionary
        rv['embedding'] = pe_embedding

        return rv  # return the return value

    def get_similarity(self,
                       first_embedding,  # embeddings of a batch of data (dim: batch_dim_1 x 32)
                       second_embedding):  # embeddings of a batch of data (dim: batch_dim_2 x 32)
        """ Get similarity scores between two embedding matrices (embeddings of batches of data).

        Args:
            first_embedding: Embeddings of a batch of data (dim: batch_dim_1 x 32)
            second_embedding: Embeddings of a batch of data (dim: batch_dim_2 x 32)
        Returns:
              Similarity matrix (dim: batch_dim_1 x batch_dim_2).
        """

        # calculate similarity score between the two embeddings using dot product
        similarity_scores = torch.matmul(first_embedding, second_embedding.T)

        # calculate probability score (estimated probability that tag 't' is a descriptor for 'x')
        # between the two embeddings
        probability_scores = self.sigmoid(similarity_scores)

        # save similarity and probability scores in result dictionary
        rv = {'similarity': similarity_scores, 'probability': probability_scores}

        # return result dictionary
        return rv

    @staticmethod
    def compute_loss(predictions,  # a dictionary of results from the Net
                     labels,  # a dictionary of labels
                     loss_wts=None):  # weights to assign to each head of the network (if it exists)
        """ Compute Net losses (optionally with SMART tags and vendor detection count auxiliary losses).

        Args:
            predictions: A dictionary of results from the Net
            labels: A dictionary of labels
            loss_wts: Weights to assign to each head of the network (if it exists); defaults to values used in the
                      ALOHA paper (1.0 for malware, 0.1 for count and each tag)
        Returns:
            Loss dictionary.
        """

        loss_dict = {'total': 0.}  # initialize dictionary of losses

        # get similarity score from model prediction
        similarity_score = predictions['similarity']

        family_labels = torch.zeros_like(similarity_score, dtype=torch.float32)
        for i in range(len(family_labels)):
            family_labels[i:int(labels[i])] = 1.0

        # extract ground truth family labels, convert them to float and allocate
        # them into the selected device (CPU or GPU)
        family_labels = family_labels.float().to(device)

        # calculate similarity loss
        similarity_loss = F.binary_cross_entropy_with_logits(similarity_score,
                                                             family_labels,
                                                             reduction='none').sum(dim=1).mean(dim=0)

        # copy calculated tags loss into the loss dictionary
        loss_dict['families'] = deepcopy(similarity_loss.item())

        # update total loss
        loss_dict['total'] += similarity_loss

        return loss_dict  # return the losses

    def normalize_results(self,
                          labels,  # labels (ground truth)
                          results_dict,  # results (predicted labels) dictionary
                          use_malware=False,  # whether or not to use malware/benignware labels as a target
                          use_count=False,  # whether or not to use the counts as an additional target
                          use_tags=False):  # whether or not to use SMART tags as additional targets
        """ Take a set of results dicts and break them out into a single dict of 1d arrays with appropriate column names
        that pandas can convert to a DataFrame.

        Args:
            labels: Labels (ground truth)
            results_dict: Results (predicted labels) dictionary
            use_malware: Whether to use malware/benignware labels as a target
            use_count: Whether to use the counts as an additional target
            use_tags: Whether to use SMART tags as additional targets. NOTE: this is here just for compatibility with
                      the evaluation procedure. With the joint embedding network the tags will always be used, even if
                      this flag is false.
        Returns:
            Dictionary containing labels and predictions.
        """

        # a lot of deepcopies are done here to avoid a FD "leak" in the dataset generator
        # see here: https://github.com/pytorch/pytorch/issues/973#issuecomment-459398189

        rv = {}  # initialize return value dict

        for column, family in enumerate(self.families):  # for all the tags
            # normalize ground truth tag array and save it into rv
            rv['label_{}_tag'.format(family)] = np.array([1.0 if lab == column else 0.0 for lab in labels])
            # normalize predicted tag array and save it into rv
            rv['pred_{}_tag'.format(family)] = Net.detach_and_copy_array(results_dict['probability'][:, column])

        return rv
