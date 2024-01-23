#!/usr/bin/env python
import json
import os, sys
from src.user.nep_work import nep_train, gen_nep_feature, nep_test
from src.user.dp_work import dp_train, dp_test
from src.user.nn_work import nn_train, gen_nn_feature, nn_test
from src.user.linear_work import linear_train, linear_test
from src.user.input_param import help_info
from src.user.active_work import ff2lmps_explore
from src.user.md_work import run_gpumd
from utils.json_operation import get_parameter, get_required_parameter
from utils.gen_multi_train import multi_train
from src.user.ckpt_extract import extract_force_field, script_model
from src.user.ckpt_compress import compress_force_field
from src.user.infer_main import infer_main

if __name__ == "__main__":
    cmd_type = sys.argv[1].upper()
    # cmd_type = "test".upper()
    # cmd_type = "train".upper()
    # cmd_type = "infer".upper()
    # cmd_type = "explore".upper()
    if cmd_type == "help".upper():
        help_info()
    elif cmd_type == "extract_ff".upper():
        ckpt_file = sys.argv[2]
        extract_force_field(ckpt_file, cmd_type)
    elif cmd_type == "compress".upper():
        ckpt_file = sys.argv[2]
        compress_force_field(ckpt_file)
    elif cmd_type == "script".upper():
        ckpt_file = sys.argv[2]
        script_model(ckpt_file)
    elif cmd_type == "infer".upper():
        ckpt_file = sys.argv[2]
        structrues_file = sys.argv[3]
        format = sys.argv[4]
        # ckpt_file = "/data/home/hfhuang/2_MLFF/2-DP/19-json-version/4-CH4-dbg/model_record/dp_model.ckpt"
        # structrues_file = "/data/home/hfhuang/2_MLFF/2-DP/19-json-version/4-CH4-dbg/POSCAR"
        infer_main(ckpt_file, structrues_file, format=format) # config or poscar
    else:
        json_path = sys.argv[2]
        # cmd_type = "test".upper()
        
        # json_path = "/data/home/hfhuang/2_MLFF/2-DP/19-json-version/4-CH4-dbg/dp_train_final.json"
        os.chdir(os.path.dirname(os.path.abspath(json_path)))
        json_file = json.load(open(json_path))
        model_type = get_required_parameter("model_type", json_file).upper()  # model type : dp or nn or linear
        model_num = get_parameter("model_num", json_file, 1)
        if model_num > 1 and cmd_type == "train".upper():
            # for multi train, need to input slurm file
            slurm_file = sys.argv[3]
            multi_train(json_path, cmd_type, slurm_file)

        if cmd_type == "train".upper():
            if model_type == "DP".upper():
                dp_train(json_file, cmd_type)
            elif model_type == "NN".upper():
                nn_train(json_file, cmd_type)
            elif model_type == "Linear".upper():
                linear_train(json_file, cmd_type)
            elif model_type == "NEP".upper():
                nep_train(json_file, cmd_type)
            else:
                raise Exception("Error! the model_type param in json file does not existent, you could use [DP/NN/LINEAR/NEP]")

                    
        elif cmd_type == "test".upper():
            if model_type == "DP".upper():
                dp_test(json_file, cmd_type)
            elif model_type == "NN".upper():
                nn_test(json_file, cmd_type)
            elif model_type == "Linear".upper():
                linear_test(json_file, cmd_type)
            elif model_type == "NEP".upper():
                nep_test(json_file, cmd_type)
            else:
                raise Exception("Error! the model_type param in json file does not existent, you could use [DP/NN/LINEAR/NEP]")
          
        elif cmd_type == "gen_feat".upper():
            if model_type == "DP".upper():
                pass
            elif model_type == "NN".upper():
                gen_nn_feature(json_file, cmd_type)
            elif model_type == "NEP".upper():
                gen_nep_feature(json_file, cmd_type)
            else:
                raise Exception("Error! the model_type param in json file does not existent, you could use [DP/NN/LINEAR/NEP]")

        elif cmd_type == "explore".upper():
            # for now, only support explore for DP model
            ff2lmps_explore(json_file)
        elif cmd_type == "gpumd".upper():
            run_gpumd(json_file)
        else:
            raise Exception("Error! the cmd type {} does not existent, you could use train or test!".format(cmd_type))
        