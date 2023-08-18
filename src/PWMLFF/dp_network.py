import os,sys
import shutil
import subprocess 
import pathlib
import random

codepath = str(pathlib.Path(__file__).parent.resolve())
sys.path.append(codepath)

#for model.mlff 
sys.path.append(codepath+'/../model')

#for default_para, data_loader_2type dfeat_sparse dp_mlff
sys.path.append(codepath+'/../pre_data')

#for optimizer
sys.path.append(codepath+'/..')
sys.path.append(codepath+'/../aux')
sys.path.append(codepath+'/../lib')
sys.path.append(codepath+'/../..')

from statistics import mode 
from turtle import Turtle, update
import torch
    
import time
import pickle
import torch.nn as nn
import math

import torch.nn as nn
import torch.nn.parallel
import torch.optim as optim
import torch.utils.data
import torch.utils.data.distributed

import time

"""
    customized modules 
"""
from model.dp_dp import DP
from optimizer.GKF import GKFOptimizer
from optimizer.LKF import LKFOptimizer
from src.pre_data.dp_data_loader import MovementDataset
from src.PWMLFF.dp_mods.dp_trainer import train_KF, train, valid, save_checkpoint, predict
from src.PWMLFF.dp_param_extract import load_davg_dstd_from_checkpoint
from src.user.model_param import DpParam
from utils.file_operation import write_arrays_to_file
#from data_loader_2type_dp import MovementDataset, get_torch_data

class dp_network:
    def __init__(self, dp_param:DpParam):
        self.dp_params = dp_param
        self.config = self.dp_params.get_dp_net_dict()
        torch.set_printoptions(precision = 12)

    def generate_data(self, is_real_Ep = False):
        stat_add = None
        if self.dp_params.inference:
            # load davg, dstd from checkpoint of model
            davg, dstd, atom_map, energy_shift = load_davg_dstd_from_checkpoint(self.dp_params.file_paths.model_path)
            stat_add = [davg, dstd, atom_map, energy_shift]
            # mkdir inference work dir and copy movement file to inference_dir/PWdata/
            if os.path.exists(self.dp_params.file_paths.test_dir) is True:
                shutil.rmtree(self.dp_params.file_paths.test_dir)
            pwdata_work_dir = os.path.join(self.dp_params.file_paths.test_dir, self.dp_params.file_paths.trainSetDir)
            os.makedirs(pwdata_work_dir)
            for i, mvm in enumerate(self.dp_params.file_paths.test_movement_path):
                mvm_dir = os.path.join(pwdata_work_dir, "{}_{}".format(os.path.basename(mvm), i))
                os.mkdir(mvm_dir)
                shutil.copy(mvm, os.path.join(mvm_dir, self.dp_params.file_paths.movement_name))
        else:
            pwdata_work_dir = os.path.abspath(self.dp_params.file_paths.trainSetDir)

        import src.pre_data.dp_mlff as dp_mlff

        cwd = os.getcwd()
        os.chdir(os.path.dirname(pwdata_work_dir))
        data_file_config = self.dp_params.get_data_file_dict()
        dp_mlff.gen_train_data(data_file_config, self.dp_params.train_egroup, self.dp_params.train_virial, is_real_Ep)
        dp_mlff.sepper_data_main(data_file_config, self.dp_params.train_egroup, stat_add=stat_add)
        os.chdir(cwd)
        return os.path.dirname(pwdata_work_dir)

    def load_and_train(self):
        best_loss = self.dp_params.best_loss
        if self.dp_params.seed is not None:
            random.seed(self.dp_params.seed)
            torch.manual_seed(self.dp_params.seed)

        if not os.path.exists(self.dp_params.store_path):
            os.mkdir(self.dp_params.store_path)

        if self.dp_params.hvd:
            import horovod.torch as hvd
            hvd.init()
            self.dp_params.gpu = hvd.local_rank()

        if torch.cuda.is_available():
            if self.dp_params.gpu:
                print("Use GPU: {} for training".format(self.dp_params.gpu))
                device = torch.device("cuda:{}".format(self.dp_params.gpu))
            else:
                device = torch.device("cuda")
        #elif torch.backends.mps.is_available():
        #    device = torch.device("mps")
        else:
            device = torch.device("cpu")

        if self.dp_params.precision == "float32":
            training_type = torch.float32  # training type is weights type
        else:
            training_type = torch.float64
        
        # Create dataset
        train_dataset = MovementDataset([os.path.join(_, "train") for _ in self.dp_params.file_paths.feature_path])
        valid_dataset = MovementDataset([os.path.join(_, "valid") for _ in self.dp_params.file_paths.feature_path])

        # create model 
        # when running evaluation, nothing needs to be done with davg.npy
        davg, dstd, ener_shift, atom_map = train_dataset.get_stat()
        stat = [davg, dstd, ener_shift]
        model = DP(self.config, device, stat)
        model = model.to(training_type)

        if not torch.cuda.is_available():
            print("using CPU, this will be slow")
        elif self.dp_params.hvd:
            if torch.cuda.is_available():
                if self.dp_params.gpu is not None:
                    torch.cuda.set_device(self.dp_params.gpu)
                    model.cuda(self.dp_params.gpu)
                    self.dp_params.batch_size = int(self.dp_params.batch_size / hvd.size())
        elif self.dp_params.gpu is not None and torch.cuda.is_available():
            torch.cuda.set_device(self.dp_params.gpu)
            model = model.cuda(self.dp_params.gpu)
        else:
            model = model.cuda()

        # define loss function (criterion), optimizer, and learning rate scheduler
        criterion = nn.MSELoss().to(device)

        if self.dp_params.optimizer_param.opt_name == "LKF":
            optimizer = LKFOptimizer(
                model.parameters(),
                self.dp_params.optimizer_param.kalman_lambda,
                self.dp_params.optimizer_param.kalman_nue,
                self.dp_params.optimizer_param.block_size
            )
        elif self.dp_params.optimizer_param.opt_name == "GKF":
            optimizer = GKFOptimizer(
                model.parameters(),
                self.dp_params.optimizer_param.kalman_lambda,
                self.dp_params.optimizer_param.kalman_nue
            )

        elif self.dp_params.optimizer_param.opt_name == "ADAM":
            optimizer = optim.Adam(model.parameters(), 
                                   self.dp_params.optimizer_param.learning_rate)
        elif self.dp_params.optimizer_param.opt_name == "SGD":
            optimizer = optim.SGD(
                model.parameters(), 
                self.dp_params.optimizer_param.learning_rate,
                momentum=self.dp_params.optimizer_param.momentum,
                weight_decay=self.dp_params.optimizer_param.weight_decay
            )
        else:
            raise Exception("Error: Unsupported optimizer!")

        # optionally resume from a checkpoint
        if self.dp_params.resume:
            model_path = self.dp_params.file_paths.model_path

            if os.path.isfile(model_path):
                print("=> loading checkpoint '{}'".format(model_path))
                if not torch.cuda.is_available():
                    checkpoint = torch.load(model_path,map_location=torch.device('cpu') )
                elif self.dp_params.gpu is None:
                    checkpoint = torch.load(model_path)
                elif torch.cuda.is_available():
                    # Map model to be loaded to specified single gpu.
                    loc = "cuda:{}".format(self.dp_params.gpu)
                    checkpoint = torch.load(model_path, map_location=loc)
                # start afresh
                self.dp_params.start_epoch = checkpoint["epoch"] + 1
                davg = checkpoint["davg"]
                dstd = checkpoint["dstd"]
                atom_map = checkpoint["atom_type_order"]
                ener_shift = checkpoint["energy_shift"]
                
                best_loss = checkpoint["best_loss"]
                model.load_state_dict(checkpoint["state_dict"])
                if "optimizer" in checkpoint:
                    optimizer.load_state_dict(checkpoint["optimizer"])
                
                # scheduler.load_state_dict(checkpoint["scheduler"])
                print("=> loaded checkpoint '{}' (epoch {})"\
                      .format(model_path, checkpoint["epoch"]))
            else:
                print("=> no checkpoint found at '{}'".format(model_path))

        if self.dp_params.hvd:
            optimizer = hvd.DistributedOptimizer(
                optimizer, named_parameters=model.named_parameters()
            )
            # Broadcast parameters from rank 0 to all other processes.
            hvd.broadcast_parameters(model.state_dict(), root_rank=0)

        # """Sets the learning rate to the initial LR decayed by 10 every 30 epochs"""
        # scheduler = StepLR(optimizer, step_size=30, gamma=0.1)

        if self.dp_params.hvd:
            train_sampler = torch.utils.data.distributed.DistributedSampler(
                train_dataset, num_replicas=hvd.size(), rank=hvd.rank()
            )
            val_sampler = torch.utils.data.distributed.DistributedSampler(
                valid_dataset, num_replicas=hvd.size(), rank=hvd.rank(), drop_last=True
            )
        else:
            train_sampler = None
            val_sampler = None

        # should add a collate function for padding
        train_loader = torch.utils.data.DataLoader(
            train_dataset,
            batch_size=self.dp_params.batch_size,
            shuffle=self.dp_params.data_shuffle,
            num_workers=self.dp_params.workers,   
            pin_memory=True,
            sampler=train_sampler,
        )
        
        val_loader = torch.utils.data.DataLoader(
            valid_dataset,
            batch_size=self.dp_params.batch_size,
            shuffle=False,
            num_workers=self.dp_params.workers,
            pin_memory=True,
            sampler=val_sampler,
        )
        
        # do inference
        if self.dp_params.inference:
            res_pd, etot_label_list, etot_predict_list, ei_label_list, ei_predict_list, force_label_list, force_predict_list\
            = predict(train_loader, model, criterion, device, self.dp_params)
            # print infos
            inference_cout = ""
            inference_cout += "For {} images: \n".format(res_pd.shape[0])
            inference_cout += "Avarage REMSE of Etot: {} \n".format(res_pd['RMSE_Etot'].mean())
            inference_cout += "Avarage REMSE of Etot per atom: {} \n".format(res_pd['RMSE_Etot_per_atom'].mean())
            inference_cout += "Avarage REMSE of Ei: {} \n".format(res_pd['RMSE_Ei'].mean())
            inference_cout += "Avarage REMSE of RMSE_F: {} \n".format(res_pd['RMSE_F'].mean())
            if self.dp_params.train_egroup:
                
                inference_cout += "Avarage REMSE of RMSE_Egroup: {} \n".format(res_pd['RMSE_Egroup'].mean())
            if self.dp_params.train_virial:
                inference_cout += "Avarage REMSE of RMSE_virial: {} \n".format(res_pd['RMSE_virial'].mean())
                inference_cout += "Avarage REMSE of RMSE_virial_per_atom: {} \n".format(res_pd['RMSE_virial_per_atom'].mean())
            
            inference_cout += "\nMore details can be found under the file directory:\n{}\n".format(os.path.realpath(self.dp_params.store_path))
            print(inference_cout)

            inference_path = self.dp_params.file_paths.test_dir
            if os.path.exists(inference_path) is False:
                os.mkdir(inference_path)
            write_arrays_to_file(os.path.join(inference_path, "etot_label.txt"), etot_label_list)
            write_arrays_to_file(os.path.join(inference_path, "etot_inference.txt"), etot_predict_list)

            write_arrays_to_file(os.path.join(inference_path, "ei_label.txt"), ei_label_list)
            write_arrays_to_file(os.path.join(inference_path, "ei_inference.txt"), ei_predict_list)

            write_arrays_to_file(os.path.join(inference_path, "force_label.txt"), force_label_list)
            write_arrays_to_file(os.path.join(inference_path, "force_inference.txt"), force_predict_list)

            res_pd.to_csv(os.path.join(inference_path, "inference_result.csv"))

            with open(os.path.join(inference_path, "inference.txt"), 'w') as wf:
                wf.writelines(inference_cout)
            return  

        if not self.dp_params.hvd or (self.dp_params.hvd and hvd.rank() == 0):
            
            train_log = os.path.join(self.dp_params.store_path, "epoch_train.dat")
            f_train_log = open(train_log, "w")

            valid_log = os.path.join(self.dp_params.store_path, "epoch_valid.dat")
            f_valid_log = open(valid_log, "w")

            # Define the lists based on the training type
            train_lists = ["epoch", "loss"]
            valid_lists = ["epoch", "loss"]

            if self.dp_params.train_energy:
                # train_lists.append("RMSE_Etot")
                # valid_lists.append("RMSE_Etot")
                train_lists.append("RMSE_Etot_per_atom")
                valid_lists.append("RMSE_Etot_per_atom")
            if self.dp_params.train_ei:
                train_lists.append("RMSE_Ei")
                valid_lists.append("RMSE_Ei")
            if self.dp_params.train_egroup:
                train_lists.append("RMSE_Egroup")
                valid_lists.append("RMSE_Egroup")
            if self.dp_params.train_force:
                train_lists.append("RMSE_F")
                valid_lists.append("RMSE_F")
            if self.dp_params.train_virial:
                # train_lists.append("RMSE_virial")
                # valid_lists.append("RMSE_virial")
                train_lists.append("RMSE_virial_per_atom")
                valid_lists.append("RMSE_virial_per_atom")

            if self.dp_params.optimizer_param.opt_name == "LKF" or self.dp_params.optimizer_param.opt_name == "GKF":
                train_lists.extend(["time"])
            else:
                train_lists.extend(["real_lr", "time"])

            train_print_width = {
                "epoch": 5,
                "loss": 18,
                "RMSE_Etot": 18,
                "RMSE_Etot_per_atom": 21,
                "RMSE_Ei": 18,
                "RMSE_Egroup": 18,
                "RMSE_F": 18,
                "RMSE_virial": 18,
                "RMSE_virial_per_atom": 23,
                "real_lr": 18,
                "time": 10,
            }

            train_format = "".join(["%{}s".format(train_print_width[i]) for i in train_lists])
            valid_format = "".join(["%{}s".format(train_print_width[i]) for i in valid_lists])

            f_train_log.write("%s\n" % (train_format % tuple(train_lists)))
            f_valid_log.write("%s\n" % (valid_format % tuple(valid_lists)))

        for epoch in range(self.dp_params.start_epoch, self.dp_params.epochs + 1):
            if self.dp_params.hvd:
                train_sampler.set_epoch(epoch)

            # train for one epoch
            time_start = time.time()
            if self.dp_params.optimizer_param.opt_name == "LKF" or self.dp_params.optimizer_param.opt_name == "GKF":
                loss, loss_Etot, loss_Etot_per_atom, loss_Force, loss_Ei, loss_egroup, loss_virial, loss_virial_per_atom = train_KF(
                    train_loader, model, criterion, optimizer, epoch, device, self.dp_params
                )
            else:
                loss, loss_Etot, loss_Etot_per_atom, loss_Force, loss_Ei, loss_egroup, loss_virial, loss_virial_per_atom, real_lr = train(
                    train_loader, model, criterion, optimizer, epoch, \
                        self.dp_params.optimizer_param.learning_rate, device, self.dp_params
                )
            time_end = time.time()

            # evaluate on validation set
            # not 
            vld_loss, vld_loss_Etot, vld_loss_Etot_per_atom, vld_loss_Force, vld_loss_Ei, val_loss_egroup, val_loss_virial, val_loss_virial_per_atom = valid(
                val_loader, model, criterion, device, self.dp_params
            )

            if not self.dp_params.hvd or (self.dp_params.hvd and hvd.rank() == 0):

                f_train_log = open(train_log, "a")
                f_valid_log = open(valid_log, "a")

                # Write the log line to the file based on the training mode
                train_log_line = "%5d%18.10e" % (
                    epoch,
                    loss,
                )
                valid_log_line = "%5d%18.10e" % (
                    epoch,
                    vld_loss,
                )

                if self.dp_params.train_energy:
                    # train_log_line += "%18.10e" % (loss_Etot)
                    # valid_log_line += "%18.10e" % (vld_loss_Etot)
                    train_log_line += "%21.10e" % (loss_Etot_per_atom)
                    valid_log_line += "%21.10e" % (vld_loss_Etot_per_atom)
                if self.dp_params.train_ei:
                    train_log_line += "%18.10e" % (loss_Ei)
                    valid_log_line += "%18.10e" % (vld_loss_Ei)
                if self.dp_params.train_egroup:
                    train_log_line += "%18.10e" % (loss_egroup)
                    valid_log_line += "%18.10e" % (val_loss_egroup)
                if self.dp_params.train_force:
                    train_log_line += "%18.10e" % (loss_Force)
                    valid_log_line += "%18.10e" % (vld_loss_Force)
                if self.dp_params.train_virial:
                    # train_log_line += "%18.10e" % (loss_virial)
                    # valid_log_line += "%18.10e" % (val_loss_virial)
                    train_log_line += "%23.10e" % (loss_virial_per_atom)
                    valid_log_line += "%23.10e" % (val_loss_virial_per_atom)

                if self.dp_params.optimizer_param.opt_name == "LKF" or self.dp_params.optimizer_param.opt_name == "GKF":
                    train_log_line += "%10.4f" % (time_end - time_start)
                else:
                    train_log_line += "%18.10e%10.4f" % (real_lr, time_end - time_start)

                f_train_log.write("%s\n" % (train_log_line))
                f_valid_log.write("%s\n" % (valid_log_line))
            
                f_train_log.close()
                f_valid_log.close()
            
            # remember best loss and save checkpoint
            is_best = vld_loss < best_loss
            best_loss = min(loss, best_loss)
            
            # should include dstd.npy and davg.npy 
            
            if not self.dp_params.hvd or (self.dp_params.hvd and hvd.rank() == 0):
                if self.dp_params.file_paths.save_p_matrix:
                    save_checkpoint(
                        {
                        "epoch": epoch,
                        "state_dict": model.state_dict(),
                        "best_loss": best_loss,
                        "davg":davg, 
                        "dstd":dstd, 
                        "energy_shift":ener_shift,
                        "atom_type_order": atom_map,    #atom type order of davg/dstd/energy_shift
                        "optimizer":optimizer.state_dict()
                        },
                        is_best,
                        self.dp_params.file_paths.model_name,
                        self.dp_params.store_path,
                    )
                else: 
                    save_checkpoint(
                        {
                        "epoch": epoch,
                        "state_dict": model.state_dict(),
                        "best_loss": best_loss,
                        "davg":davg, 
                        "dstd":dstd, 
                        "energy_shift":ener_shift,
                        "atom_type_order": atom_map,    #atom type order of davg/dstd/energy_shift
                        },
                        is_best,
                        self.dp_params.file_paths.model_name,
                        self.dp_params.store_path,
                    )
                
    
    def evaluate(self,num_thread = 1):
        """
            evaluate a model against AIMD
            put a MOVEMENT in /MD and run MD100 
        """
        if not os.path.exists("MD/MOVEMENT"):
            raise Exception("MD/MOVEMENT not found")
        import md100
        md100.run_md100(imodel = 5, atom_type = self.dp_params.atom_type, num_process = num_thread) 
        
    def plot_evaluation(self):
        if not os.path.exists("MOVEMENT"):
            raise Exception("MOVEMENT not found. It should be force field MD result")
        import src.aux.plot_evaluation as plot_evaluation
        plot_evaluation.plot()

    def run_md(self, init_config = "atom.config", md_details = None, num_thread = 1,follow = False):
        import subprocess 

        # remove existing MOVEMENT file for not 
        if follow == False:
            os.system('rm -f MOVEMENT')     
        
        if md_details is None:
            raise Exception("md detail is missing")
        
        md_detail_line = str(md_details)[1:-1]+"\n"
        
        if os.path.exists(init_config) is not True: 
            raise Exception("initial config for MD is not found")
        
        # preparing md.input 
        f = open('md.input', 'w')
        f.write(init_config+"\n")

        f.write(md_detail_line) 
        f.write('F\n')
        f.write("5\n")     # imodel=1,2,3.    {1:linear;  2:VV;   3:NN, 5: dp 
        f.write('1\n')               # interval for MOVEMENT output
        f.write('%d\n' % len(self.dp_params.atom_type)) 
        
        for i in range(len(self.dp_params.atom_type)):
            f.write('%d %d\n' % (self.dp_params.atom_type[i], 2*self.dp_params.atom_type[i]))
        f.close()    
        
        # creating md.input for main_MD.x 
        command = r'mpirun -n ' + str(num_thread) + r' main_MD.x'
        print (command)
        subprocess.run(command, shell=True) 
