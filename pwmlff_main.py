#!/usr/bin/env python
import json
import os, sys

from src.user.dp_work import dp_train, gen_dp_feature, dp_test
from src.user.nn_work import nn_train, gen_nn_feature, nn_test
from src.user.linear_work import linear_train, linear_test
from src.user.model_param import help_info
from utils.json_operation import get_parameter, get_required_parameter

if __name__ == "__main__":
    cmd_type = sys.argv[1].upper()

    if cmd_type == "help".upper():
        help_info()
    else:
        json_path = sys.argv[2]
        # cmd_type = "test".upper()
        
        # os.chdir("/data/home/wuxingxing/datas/pwmat_mlff_workdir/cu/nn/nn_34")
        os.chdir(os.path.abspath(os.path.dirname(json_path)))
        json_file = json.load(open(json_path))
        model_type = get_required_parameter("model_type", json_file).upper()  # model type : dp or nn or linear
        
        if cmd_type == "train".upper():
            if model_type == "DP".upper():
                dp_train(json_file, cmd_type)
            elif model_type == "NN".upper():
                nn_train(json_file, cmd_type)
            elif model_type == "Linear".upper():
                linear_train(json_file, cmd_type)
            else:
                raise Exception("Error! the model_type param in json file does not existent, you could use DP or NN or Linear")
            
        elif cmd_type == "test".upper():
            if model_type == "DP".upper():
                dp_test(json_file, cmd_type)
            elif model_type == "NN".upper():
                nn_test(json_file, cmd_type)
            elif model_type == "Linear".upper():
                linear_test(json_file, cmd_type)
            else:
                raise Exception("Error! the model_type param in json file does not existent, you could use DP or NN or Linear")

        else:
            raise Exception("Error! the cmd type {} does not existent, you could use train or test!".format(cmd_type))
        
