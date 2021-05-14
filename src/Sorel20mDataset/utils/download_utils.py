import os

needed_objects = {"meta": "09-DEC-2020/processed-data/meta.db",
                  "lock": "09-DEC-2020/processed-data/ember_features/lock.mdb",
                  "data": "09-DEC-2020/processed-data/ember_features/data.mdb",
                  "missing": "09-DEC-2020/processed-data/shas_missing_ember_features.json"}


def _check_files(destination_dir):  # path to the destination folder where to save the element to

    # select just the objects not already present
    objects_to_download = {key: obj for key, obj in needed_objects.items()
                           if not os.path.exists(os.path.join(destination_dir, obj))}

    # if there are no objects to download return true
    return len(objects_to_download) == 0
