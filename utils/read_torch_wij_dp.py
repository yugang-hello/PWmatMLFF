#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
	Author: L. Wang
	Created in: April 2022
	
	Extract Wij and Bi from .pt file generated by KFDP. 


"""
import os
import sys
import numpy as np

#get the current working directory
sys.path.append(os.getcwd())

#get the abs path of this file
codepath=os.path.abspath(sys.path[0])

sys.path.append(codepath+'/../src/pre_data')
sys.path.append(codepath+'/..')
print (codepath)

import use_para as pm
import parse_input
parse_input.parse_input()

#import parameters as pm
import torch



def getOrderedAtom():
    """
        get atom index with the same order as atom.config
    """
    movement_name = "atom.config"


    ff = open(movement_name,"r")

    mvt_tmp = ff.readlines()
    

    mvt = [] 
    for item in mvt_tmp:
        mvt.append(item.split())
    knot = False

    num_atom = int(mvt[0][0])
    print ("atom number:" + str(num_atom))

    ordered_atomtype = [] 

    uom = {} 

    num_passed = 0 ; 

    for line in mvt:
        if knot:
            if line[0] not in uom:
                uom[line[0]] = True
                ordered_atomtype.append(line[0])
                
            num_passed +=1;        
            if num_passed == num_atom:
                break; 

        if line[0] == "Position":
            knot = True
    # list of string
    return ordered_atomtype

def catNameEmbedingW(idxNet, idxLayer):
	return "embeding_net."+str(idxNet)+".weights.weight"+str(idxLayer)

def catNameEmbedingB(idxNet, idxLayer):
	return "embeding_net."+str(idxNet)+".bias.bias"+str(idxLayer)

def catNameFittingW(idxNet, idxLayer):
	return "fitting_net."+str(idxNet)+".weights.weight"+str(idxLayer)

def catNameFittingB(idxNet, idxLayer):
	return "fitting_net."+str(idxNet)+".bias.bias"+str(idxLayer)

def catNameFittingRes(idxNet, idxResNet):
	return "fitting_net."+str(idxNet)+".resnet_dt.resnet_dt"+str(idxResNet)


def dump(item, f):
	raw_str = ''
	for num in item:
		raw_str += (str(float(num))+' ')
	f.write(raw_str)
	f.write('\n')
	#return raw_str

"""
"""

kfdp = False

netConfig = pm.DP_cfg_dp if kfdp==False else pm.DP_cfg_dp_kf

isEmbedingNetResNet = netConfig["embeding_net"]["resnet_dt"]
isFittingNetResNet  = netConfig["fitting_net"]["resnet_dt"]

embedingNetSizes = netConfig['embeding_net']['network_size']
nLayerEmbedingNet = len(embedingNetSizes)

print("layer number of embeding net:"+str(nLayerEmbedingNet))
print("size of each layer"+ str(embedingNetSizes) + '\n')

fittingNetSizes = netConfig['fitting_net']['network_size']
nLayerFittingNet = len(fittingNetSizes)

print("layer number of fitting net:"+str(nLayerFittingNet))
print("size of each layer"+ str(fittingNetSizes) + '\n')

embedingNet_output = 'embeding.net' 
fittingNet_output = 'fitting.net'

pt_name = r"record/model/better.pt" # modify according to your need 

raw = torch.load(pt_name,map_location=torch.device("cpu"))['model']
tensor_list = list(raw.keys())

#determining # of networks 
nEmbedingNet = len(pm.atomType)**2  
nFittingNet = len(pm.atomType)
    
"""
	write embedding network
"""

f = open(embedingNet_output, 'w')

# total number of embeding network
f.write(str(nEmbedingNet)+'\n') 

#layer of embeding network
f.write(str(nLayerEmbedingNet) + '\n')

#size of each layer

f.write("1 ")
for i in embedingNetSizes:
	f.write(str(i)+' ')

f.write('\n')

#f.writelines([str(i) for i in embedingNetSizes])
	
print("******** converting embeding network starts ********")
for idxNet in range(nEmbedingNet):
	print ("converting embeding network No."+str(idxNet))
	for idxLayer in range(nLayerEmbedingNet):
		print ("converting layer "+str(idxLayer) )	

		#write wij
		label_W = catNameEmbedingW(idxNet,idxLayer)
		for item in raw[label_W]:
			dump(item,f)

		print("w matrix dim:" +str(len(raw[label_W])) +str('*') +str(len(raw[label_W][0])))

		#write bi
		label_B = catNameEmbedingB(idxNet,idxLayer)
		dump(raw[label_B][0],f)
		print ("b dim:" + str(len(raw[label_B][0])))

	print ('\n')
		#break
f.close()

print("******** converting embeding network ends  *********")

"""
    write fitting network
"""

f = open(fittingNet_output, 'w')

# total number of embeding network
f.write(str(nFittingNet)+'\n') 

#layer of embeding network
f.write(str(nLayerFittingNet) + '\n')

#size of each layer

f.write(str(len(raw[catNameFittingW(0,0)]))+' ')

for i in fittingNetSizes:
    f.write(str(i)+' ')

f.write('\n')

print("******** converting fitting network starts ********")
for idxNet in range(nFittingNet):
    print ("converting fitting network No."+str(idxNet))
    for idxLayer in range(nLayerFittingNet):
        print ("converting layer "+str(idxLayer) )  

        #write wij
        label_W = catNameFittingW(idxNet,idxLayer)
        for item in raw[label_W]:
            dump(item,f)

        print("w matrix dim:" +str(len(raw[label_W])) +str('*') +str(len(raw[label_W][0])))

        #write bi
        label_B = catNameFittingB(idxNet,idxLayer)
        dump(raw[label_B][0],f)
        print ("b dim:" + str(len(raw[label_B][0])))

    print ('\n')
        #break
f.close()

print("******** converting fitting network ends  *********")

"""
	writing ResNets
"""
print("******** converting resnet starts  *********")
if isFittingNetResNet:
    numResNet = 0

    """


    for keys in list(raw.keys()):
        tmp = keys.split('.')
        if tmp[0] == "fitting_net" and tmp[1] == '0' and tmp[2] == 'resnet_dt':
            numResNet +=1 

    print ("number of resnet: " + str(numResNet))

    filename  = "fittingNet.resnet"

    f= open(filename, "w")
    
    f.write(str(numResNet)+"\n")

    for fittingNetIdx in range(nFittingNet):
        for resNetIdx in range(1,numResNet+1):
            f.write(str(fittingNetSizes[i+1])+"\n")
            label_resNet = catNameFittingRes(fittingNetIdx,resNetIdx)
            dump(raw[label_resNet][0],f)

    """ 

    """
		The format below fits Dr.Wang's Fortran routine
    """

    for keys in list(raw.keys()):
        tmp = keys.split('.')
        if tmp[0] == "fitting_net" and tmp[1] == '0' and tmp[2] == 'resnet_dt':
            numResNet +=1 

    print ("number of resnet: " + str(numResNet))

    filename  = "fittingNet.resnet"


    f= open(filename, "w")
    
    # itype: number of fitting network 
    f.write(str(nFittingNet)+'\n') 

    #nlayer: 
    f.write(str(nLayerFittingNet) + '\n')

    #dim of each layer 
    f.write(str(len(raw[catNameFittingW(0,0)]))+' ')

    for i in fittingNetSizes:
        f.write(str(i)+' ')	
    f.write("\n")

    for i in range(0,len(fittingNetSizes)+1):
        if (i > 1) and (i < len(fittingNetSizes)):
            f.write("1 ")
        else:
            f.write("0 ")

    f.write("\n")


    #f.write(str(numResNet)+"\n")

    for fittingNetIdx in range(nFittingNet):
        for resNetIdx in range(1,numResNet+1):
            f.write(str(fittingNetSizes[resNetIdx])+"\n")
            label_resNet = catNameFittingRes(fittingNetIdx,resNetIdx)   
            dump(raw[label_resNet][0],f)

    f.close()

print("******** converting resnet ends  *********\n")


"""
    generating the deepMD.in 
"""

print("******** generating gen_dp.in  *********")

orderedAtomList = getOrderedAtom()

davg = np.load("davg.npy")
dstd = np.load("dstd.npy")

davg_size = len(davg)
dstd_size = len(dstd)

assert(davg_size == dstd_size)
assert(davg_size == len(orderedAtomList))

f_out = open("gen_dp.in","w")

# in default_para.py, Rc_M = 6.0 Rc_min = 5.8. This is also used for feature generations 

f_out.write(str(pm.Rc_M) + ' ') 
f_out.write(str(pm.maxNeighborNum)+"\n")
f_out.write(str(dstd_size)+"\n")

for i,atom in enumerate(orderedAtomList):
    f_out.write(atom+"\n")
    f_out.write(str(pm.Rc_M)+' '+str(pm.Rc_min)+'\n')

    # davg 
    # dstd 

    for idx in range(4):
        f_out.write(str(davg[i][idx])+" ")
    
    f_out.write("\n")

    for idx in range(4):
        f_out.write(str(dstd[i][idx])+" ")
    f_out.write("\n")

f_out.close() 

print("******** gen_dp.in generation done *********")
