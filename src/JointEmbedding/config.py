# modify these paths as needed to point to the directory that contains the meta_db,
# to indicate where the checkpoints should be placed during model training
# and to indicate where the results should be placed
db_path = '/content/Dataset/09-DEC-2020/processed-data'
checkpoint_dir = '/content/drive/MyDrive/thesis/Checkpoints/Checkpoints_JE_100k'
results_dir = '/content/drive/MyDrive/thesis/Results/Results_JE_100k'

# set this to the desired device, e.g. 'cuda:0' if a GPU is available, otherwise 'cpu'
device = 'cuda:0'
# device = 'cpu'

# adjust the batch size as needed given memory/bus constraints
batch_size = 8192  # 8192

# NOTE -- if you change the below values, your results will not be comparable with those from
# 		  other users of this data set.

# This is the timestamp that divides the validation data (used to check convergence/overfitting)
# from test data (used to assess final performance)
validation_test_split = 1547279640.0
# This is the timestamp that splits training data from validation data
train_validation_split = 1543542570.0

# max number of training data samples to use (if 'None' -> takes all)
training_n_samples_max = 100000
# max number of validation data samples to use (if 'None' -> takes all)
validation_n_samples_max = 19231
# max number of test data samples to use (if 'None' -> takes all)
test_n_samples_max = 30769
