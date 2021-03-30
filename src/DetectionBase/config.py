import baker  # Easy, powerful access to Python functions from the command line

class Config(object):
    # NOTE -- if you change the "validation_test_split" and/or "train_validation_split" values, your results will not
    #         be comparable with those from other users of this data set.

    def __init__(self,
                 db_path, # path to the directory that contains the meta_db
                 checkpoint_dir, # path where to save the model training checkpoints to
                 runs = 5,  # how many times to run the model (training + evaluation) to plot mean and confidence of the results
                 device = 'cuda:0', # set this to the desired device, e.g. 'cuda:0' if a GPU is available, 'cpu' otherwise
                 validation_test_split = 1547279640.0,  # timestamp that divides the validation data (used to check convergence/overfitting) from test data (used to assess final performance)
                 train_validation_split = 1543542570.0, # timestamp that splits training data from validation data
                 batch_size = 8192):  # Dataloader batch size (change as needed given memory/bus constraints)
      
        self.device = device
        self.validation_test_split = validation_test_split
        self.train_validation_split = train_validation_split
        self.db_path = db_path
        self.checkpoint_dir = checkpoint_dir
        self.batch_size = batch_size
        self.runs = runs

        # create directory path if it does not exist (it succeeds even if the directory already exists)
        os.makedirs(checkpoint_dir, exist_ok=True)

				
@baker.command
def configure(db_path, # path to the directory that contains the meta_db
              checkpoint_dir, # path where to save the model training checkpoints to
              runs = 5,  # how many times to run the model (training + evaluation) to plot mean and confidence of the results
              device = 'cuda:0', # set this to the desired device, e.g. 'cuda:0' if a GPU is available, 'cpu' otherwise
              validation_test_split = 1547279640.0,  # timestamp that divides the validation data (used to check convergence/overfitting) from test data (used to assess final performance)
              train_validation_split = 1543542570.0, # timestamp that splits training data from validation data
              batch_size = 8192):  # Dataloader batch size (change as needed given memory/bus constraints)
		"""
    Configure base Detection model.
		NOTE -- if you change the "validation_test_split" and/or "train_validation_split" values, your results will not
    				be comparable with those from other users of this data set.
   
		:param db_path: Path to the directory that contains the meta_db
		:param checkpoint_dir: Path where to save the model training checkpoints to
		:param runs: How many times to run the model (training + evaluation) to plot mean and confidence of the results; defaults to 5
		:param device: Set this to the desired device, e.g. 'cuda:0' if a GPU is available, 'cpu' otherwise; defaults to 'cuda:0'
		:param validation_test_split: Timestamp that divides the validation data (used to check convergence/overfitting)
				from test data (used to assess final performance); defaults to 1547279640.0
		:param train_validation_split: Timestamp that splits training data from validation data; defaults to 1543542570.0
		:param batch_size: Dataloader batch size (change as needed given memory/bus constraints); defaults to 8192
    """
		
		# instantiate configuration object
		global config = Config(db_path = db_path,
				       checkpoint_dir = checkpoint_dir,
				       runs = runs,
				       device = device,
				       validation_test_split = validation_test_split,
				       train_validation_split = train_validation_split,
				       batch_size = batch_size)
		
		
if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
