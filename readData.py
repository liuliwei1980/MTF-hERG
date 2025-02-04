import numpy as np
import pandas as pd
from rdkit import Chem
from rdkit.Chem import Draw
from rdkit.Chem import AllChem
import pandas as pd
import numpy as np
import torch.nn.functional as F
import os
import random
import json, pickle
from collections import OrderedDict
from rdkit import Chem
from rdkit.Chem import MolFromSmiles
import networkx as nx
import torch
def all_data():
    csv_file_path = './hEGR.csv'
    df = pd.read_csv(csv_file_path)
    smiles = df['SMILES']
    label = df['label']
    labelList = []
    n=[0,1]
    p=[1,0]
    for iteml in label:
        if iteml == 0:
            labelList.append(n)
        if iteml == 1:
            labelList.append(p)
    list_of_arrays = []
    list_of_ecfp = []
    list_of_hash = []
    list_of_node = []
    list_of_edge = []
    list_of_pos = []
    fingerprint_radius = 2
    fingerprint_length = 1024
    for item in smiles:
        # 视觉Imgae特征
        mol = Chem.MolFromSmiles(item)
        mol_image = Draw.MolToImage(mol, size=(224, 224))
        numpy_image = np.array(mol_image)
        list_of_arrays.append(numpy_image)
        # ecfp_np和hash特征
        ecfp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=1024)
        ecfp_np = np.array(ecfp)
        list_of_ecfp.append(ecfp_np)
        fingerprint = AllChem.GetHashedMorganFingerprint(mol, fingerprint_radius, nBits=fingerprint_length)
        fingerprint_np = np.zeros((fingerprint_length,), dtype=np.int8)
        for idx in fingerprint.GetNonzeroElements():
            fingerprint_np[idx] = 1
        list_of_hash.append(fingerprint_np)
        # 图神经网络特征
        atom_3dcoords = get_MMFF_atom_poses(mol, numConfs=None, return_energy=False)
        pos = torch.tensor(np.array(atom_3dcoords), dtype=torch.float)
        pos = adjust_node(pos,3)
        features, edge_tensor = smile_to_graph(item)
        features = np.array(features)
        features = torch.tensor(features)
        features = adjust_node(features,78)
        edge_tensor = np.array(edge_tensor)
        edge_tensor = torch.tensor(edge_tensor)
        edge_tensor = adjust_edge(edge_tensor)
        list_of_node.append(features)
        list_of_edge.append(edge_tensor)
        list_of_pos.append(pos)

    graphImg = np.stack(list_of_arrays, axis=0)
    ecfp = np.stack(list_of_ecfp, axis=0)
    hash = np.stack(list_of_hash, axis=0)
    return graphImg, ecfp, hash,list_of_node,list_of_edge, list_of_pos,label



#%% 工具方法
def adjust_node(tensor,n_size):
    target_size = (30, n_size)
    n, _ = tensor.shape
    if n > target_size[0]:
        tensor = tensor[:target_size[0], :]
    elif n < target_size[0]:
        padding = torch.zeros(target_size[0] - n, n_size, dtype=tensor.dtype)
        tensor = torch.cat((tensor, padding), dim=0)
    return tensor
def get_MMFF_atom_poses(mol, numConfs=None, return_energy=False):
    """the atoms of mol will be changed in some cases."""
    try:
        new_mol = Chem.AddHs(mol)
        res = AllChem.EmbedMultipleConfs(new_mol, numConfs=numConfs)
        ### MMFF generates multiple conformations
        res = AllChem.MMFFOptimizeMoleculeConfs(new_mol)
        new_mol = Chem.RemoveHs(new_mol)
        index = np.argmin([x[1] for x in res])
        #energy = res[index][1]
        conf = new_mol.GetConformer(id=int(index))
    except:
        new_mol = mol
        AllChem.Compute2DCoords(new_mol)
        #energy = 0
        conf = new_mol.GetConformer()

    atom_poses = get_atom_poses(new_mol, conf)

    return atom_poses
smile_changed = {}
def get_atom_poses(mol, conf):
    """tbd"""
    atom_poses = []
    for i, atom in enumerate(mol.GetAtoms()):
        if atom.GetAtomicNum() == 0:
            return [[0.0, 0.0, 0.0]] * len(mol.GetAtoms())
        pos = conf.GetAtomPosition(i)
        atom_poses.append([pos.x, pos.y, pos.z])
    return atom_poses
def adjust_edge(matrix):
    # 检查输入矩阵的维度
    if len(matrix.shape) != 2 or matrix.shape[1] != 2:
        raise ValueError("Input must be a matrix of shape (n, 2).")

        # 获取原始矩阵的行数
    n = matrix.shape[0]

    # 如果原始矩阵的行数大于70，则裁剪为70行
    if n > 70:
        matrix = matrix[:70, :]
        # 如果原始矩阵的行数小于70，则用0填充至70行
    elif n < 70:
        padding_size = 70 - n
        padding = np.zeros((padding_size, 2))
        matrix = np.vstack((matrix, padding))

    return matrix
def atom_features(atom):
    # 44 +11 +11 +11 +1
    return np.array(one_of_k_encoding_unk(atom.GetSymbol(),
                                          ['C', 'N', 'O', 'S', 'F', 'Si', 'P', 'Cl', 'Br', 'Mg', 'Na', 'Ca', 'Fe', 'As',
                                           'Al', 'I', 'B', 'V', 'K', 'Tl', 'Yb', 'Sb', 'Sn', 'Ag', 'Pd', 'Co', 'Se',
                                           'Ti', 'Zn', 'H', 'Li', 'Ge', 'Cu', 'Au', 'Ni', 'Cd', 'In', 'Mn', 'Zr', 'Cr',
                                           'Pt', 'Hg', 'Pb', 'X']) +
                    one_of_k_encoding(atom.GetDegree(), [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]) +
                    one_of_k_encoding_unk(atom.GetTotalNumHs(), [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]) +
                    one_of_k_encoding_unk(atom.GetImplicitValence(), [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]) +
                    [atom.GetIsAromatic()])

# mol smile to mol graph edge index

def one_of_k_encoding(x, allowable_set):
    if x not in allowable_set:
        # print(x)
        raise Exception('input {0} not in allowable set{1}:'.format(x, allowable_set))
    return list(map(lambda s: x == s, allowable_set))

def one_of_k_encoding_unk(x, allowable_set):
    '''Maps inputs not in the allowable set to the last element.'''
    if x not in allowable_set:
        x = allowable_set[-1]
    return list(map(lambda s: x == s, allowable_set))





def edge_index_to_adjacency_matrix(edge_index, num_nodes):
    # 创建一个大小为num_nodes x num_nodes的零矩阵
    adjacency_matrix = np.zeros((num_nodes, num_nodes), dtype=int)
    # 遍历edge index，将矩阵中对应的元素设置为1
    for edge in edge_index:
        node1, node2 = edge
        adjacency_matrix[node1, node2] = 1
        adjacency_matrix[node2, node1] = 1  # 对于无向图，需要设置对称位置的值

    return adjacency_matrix




def smile_to_graph(smile):
    mol = Chem.MolFromSmiles(smile)
    c_size = mol.GetNumAtoms()
    features = []
    for atom in mol.GetAtoms():
        feature = atom_features(atom)
        features.append(feature / sum(feature))
    edges = []
    for bond in mol.GetBonds():
        edges.append([bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()])
    g = nx.Graph(edges).to_directed()
    edge_index = []
    mol_adj = np.zeros((c_size, c_size))
    for e1, e2 in g.edges:
        mol_adj[e1, e2] = 1
    mol_adj += np.matrix(np.eye(mol_adj.shape[0]))
    index_row, index_col = np.where(mol_adj >= 0.5)
    for i, j in zip(index_row, index_col):
        edge_index.append([i, j])
    # edge_tensor = edge_index_to_adjacency_matrix(edge_index, c_size)
    return  features, edge_index
#%%

