import data.get_cmap as gc
import data.data as d
from main import metrics
from main import confmat
import models.dscript_like as dscript_like
import models.baseline2d as baseline2d
import models.fc2_20_2_dense as richoux
import models.attention as attention
import numpy as np
from Bio.SeqUtils import seq1
from Bio.SeqUtils import seq3
from Bio import Align
import Bio.PDB
import os
import requests
import pickle
import torch
import torch.nn as nn
import torch.utils.data as data
import matplotlib.pyplot as plt
import pandas as pd
import warnings

def main(dataset='Intra1', model='TUnA'):
    warnings.filterwarnings("ignore")
    confpred_dict = load_dict(dataset, model)
    seq_data = "/nfs/home/students/t.reim/bachelor/pytorchtest/data/gold_stand/gold_stand_train_all_seq.csv"
    df = pd.read_csv(seq_data)
    for interaction in list(confpred_dict.keys()):
        list_interaction = list(interaction)
        id1 = list_interaction[0]
        id2 = list_interaction[1]
        complex_id = confpred_dict[interaction]
        pdb_file = download_pdb_files([complex_id])
        '''
        real_cmap = gc.get_cmap(pdb_filename=pdb_file)
        start_pos_seq1, end_pos_seq1 = int(real_cmap.index[0].split(':')[1]), int(real_cmap.index[-1].split(':')[1])
        start_pos_seq2, end_pos_seq2 = int(real_cmap.columns[0].split(':')[1]), int(real_cmap.columns[-1].split(':')[1])
        #gc.plot_cmap(real_cmap)
        '''
        print(f'Interaction: {id1} - {id2}: {complex_id}')
        distmap, x0_labels, y0_labels, x1_labels, y1_labels, start_pos_seq1, end_pos_seq1, start_pos_seq2, end_pos_seq2, num_chains = aligned_distmap(id1, id2, complex_id, pdb_file, df)
        #if num_chains > 4:
        #    print(f'Number of chains in {complex_id} is {num_chains}. Skipping...')
        #    continue
        pred_dist = get_pred_cmap(id1, id2, complex_id, model=model, emb_name='esm2_t33_650', emb_type='per_tok')
        pred_dist_cut = pred_dist[start_pos_seq1:end_pos_seq1, start_pos_seq2:end_pos_seq2]
        cor = gc.plot_distmaps(distmap, pred_dist_cut, x0_labels, y0_labels, x1_labels, y1_labels, complex_id, id1, id2)
        #gc.plot_distmap(distmap, x0_labels, y0_labels)
        #gc.plot_distmap(pred_dist_cut, x1_labels, y1_labels)

def load_dict(dataset, model):
    with open(f'/nfs/home/students/t.reim/bachelor/pytorchtest/data/gold_stand/confpred_dict_{dataset}_{model}.pkl', 'rb') as f:
        return pickle.load(f)
    
def aligned_distmap(id1, id2, pdb_id, pdb_file, seq_df):
    structure = Bio.PDB.PDBParser().get_structure(pdb_id, pdb_file)
    prot_to_cs = get_protein_to_chains_mapping(pdb_file)
    chains_seqs = {chain.id: seq1(''.join(residue.resname for residue in chain)) for chain in structure.get_chains()}

    row = seq_df[((seq_df['Id1'] == id1) | (seq_df['Id2'] == id1)) & ((seq_df['Id1'] == id2) | (seq_df['Id2'] == id2))]
    seq_a = row['sequence_a'].values[0]
    seq_b = row['sequence_b'].values[0]

    if id1 in row['Id2'].values and id2 in row['Id1'].values:
        # Swap id1 and id2
        id1, id2 = id2, id1
        seq_a, seq_b = seq_b, seq_a

    print(f'Number of chains in {pdb_id}: {len(chains_seqs)}')
    chain_prot1 = prot_to_cs[id1][0]
    chain_prot2 = prot_to_cs[id2][0]
    print(f'Chains: {id1}: {chain_prot1}, {id2}: {chain_prot2}')

    aligner = Align.PairwiseAligner()
    aligner.mode = 'local'
    aligner.open_gap_score = -100

    alignmentA = aligner.align(seq_a, chains_seqs[chain_prot1])[0]
    alignment_start_seq_a, alignment_end_seq_a = alignmentA.coordinates[0]
    alignment_start_chain_a, alignment_end_chain_a = alignmentA.coordinates[1]

    alignmentB = aligner.align(seq_b, chains_seqs[chain_prot2])[0]
    alignment_start_seq_b, alignment_end_seq_b = alignmentB.coordinates[0]
    alignment_start_chain_b, alignment_end_chain_b = alignmentB.coordinates[1]

    distmap, x0, y0 = get_distmap(structure, alignment_start_chain_a, alignment_end_chain_a, alignment_start_chain_b, alignment_end_chain_b,
                                  chain_prot1, chain_prot2)

    x1 = one_to_three(seq_b, alignment_start_seq_b, alignment_end_seq_b)
    y1 = one_to_three(seq_a, alignment_start_seq_a, alignment_end_seq_a)

    return distmap, x0, y0, x1, y1, alignment_start_seq_a, alignment_end_seq_a, alignment_start_seq_b, alignment_end_seq_b, len(chains_seqs)

def get_distmap(structure, start_A, end_A, start_B, end_B, chain_prot1, chain_prot2):
    model = structure[0]
    chain_1 = [res for i, res in enumerate(model[chain_prot1]) if start_A <= i < end_A]
    chain_2 = [res for i, res in enumerate(model[chain_prot2]) if start_B <= i < end_B]
    dist_matrix = calc_dist_matrix(chain_1, chain_2)
    x = [f"{str(res.resname)}:{str(res.id[1])}" for res in chain_2]
    y = [f"{str(res.resname)}:{str(res.id[1])}" for res in chain_1]
    return dist_matrix, x, y   

def calc_dist_matrix(chain_one, chain_two) :
    """Returns a matrix of C-alpha distances between two chains"""
    answer = np.zeros((len(chain_one), len(chain_two)), np.float64)
    for row, residue_one in enumerate(chain_one) :
        for col, residue_two in enumerate(chain_two) :
            answer[row, col] = calc_residue_dist(residue_one, residue_two)
    return answer

def calc_residue_dist(residue_one, residue_two) :
    """Returns the C-alpha distance between two residues"""
    if "CA" not in residue_one or "CA" not in residue_two:
        return np.nan
    diff_vector  = residue_one["CA"].coord - residue_two["CA"].coord
    return np.sqrt(np.sum(diff_vector * diff_vector))

def one_to_three(seq, start, end):
    seq = seq[start:end]
    return [f"{seq3(residue).upper()}:{i+start}" for i, residue in enumerate(seq)]

def get_pred_cmap(id1, id2, complex_id, model, emb_name='esm2_t33_650', emb_type='per_tok'):
    model_path = f'/nfs/home/students/t.reim/bachelor/pytorchtest/models/pretrained/{model}_{emb_name}.pt'
    layer = int(emb_name.split('t')[1].split('_')[0])
    emb_dir = "/nfs/scratch/t.reim/embeddings/" + emb_name + "/" + emb_type + "/"

    #add way to load different models
    model = get_model(model, emb_sizes[emb_name])
    model.load_state_dict(torch.load(model_path, map_location=torch.device('cpu')))

    seq1 = d.get_embedding_per_tok(emb_dir, id1, layer).unsqueeze(0)
    seq2 = d.get_embedding_per_tok(emb_dir, id2, layer).unsqueeze(0)
    model.eval()
    pred, cmap = model(seq1, seq2)
    print(f'{complex_id}: {pred}')
    cmap = cmap.squeeze().detach().numpy() 
    return cmap

def plot_predcmap(cmap, name):
    plt.imshow(cmap, cmap='hot')
    plt.colorbar()
    plt.savefig(f'/nfs/home/students/t.reim/bachelor/pytorchtest/plots/contact_map_{name}.png')
    plt.clf()

def get_protein_to_chains_mapping(pdb_file):
    protein_to_chain = {}
    with open(pdb_file, 'r') as f:
        for line in f:
            if line.startswith('DBREF'):
                fields = line.split()
                chain_id = fields[2]
                uniprot_id = fields[6]
                if uniprot_id not in protein_to_chain:
                    protein_to_chain[uniprot_id] = []
                protein_to_chain[uniprot_id].append(chain_id)
    return protein_to_chain

def download_pdb_files(complex_ids, directory='/nfs/home/students/t.reim/bachelor/pytorchtest/data/pdb_files'):
    if not os.path.exists(directory):
        os.makedirs(directory)

    for pdb_id in complex_ids:
        file_path = os.path.join(directory, f'{pdb_id}.pdb')

        if not os.path.exists(file_path):
            url = f'https://files.rcsb.org/download/{pdb_id}.pdb'
            response = requests.get(url)

            if response.status_code == 200:
                with open(file_path, 'w') as file:
                    file.write(response.text)
            else:
                print(f'Failed to download PDB file for {pdb_id}')
    
    return file_path            

emb_sizes = {
    'esm2_t48_3B': 5120,
    'esm2_t36_650M': 2560,
    'esm2_t33_650': 1280
}

def get_model(model_name, insize, h3=64, num_heads=8, dropout=0.2, ff_dim=256, pooling='avg', kernel_size=2,
              rffs=256, cross=False, d_=64, w=64, h=64, x0=0, k=1, pool_size=2, do_pool=True, do_w=True,
              theta_init=1e-3, lambda_init=1e-3, gamma_init=1e-3, ff_dim1=512, ff_dim2=256, ff_dim3=128, spec_norm=False):
    model_mapping = {
        "dscript_like": dscript_like.DScriptLike(embed_dim=insize, d=d_, w=w, h=h, x0=x0, k=k, pool_size=pool_size, do_pool=do_pool,
                                                    do_w=do_w, theta_init=theta_init, lambda_init=lambda_init, gamma_init=gamma_init),
        "richoux": richoux.FC2_20_2Dense(embed_dim=insize, ff_dim1=ff_dim1, ff_dim2=ff_dim2, ff_dim3=ff_dim3, spec_norm=spec_norm),
        "baseline2d": baseline2d.baseline2d(embed_dim=insize, h3=h3, kernel_size=kernel_size, pooling=pooling),
        "selfattention": attention.SelfAttInteraction(embed_dim=insize, num_heads=num_heads, h3=h3, dropout=dropout,
                                                        ff_dim=ff_dim, pooling=pooling, kernel_size=kernel_size),
        "crossattention": attention.CrossAttInteraction(embed_dim=insize, num_heads=num_heads, h3=h3, dropout=dropout,
                                                        ff_dim=ff_dim, pooling=pooling, kernel_size=kernel_size),
        "ICAN_cross": attention.ICAN_cross(embed_dim=insize, num_heads=num_heads, cnn_drop=dropout, transformer_drop=dropout, hid_dim=h3, ff_dim=ff_dim),
        "AttDscript": attention.AttentionDscript(embed_dim=insize, num_heads=num_heads, dropout=dropout, d=h3, w=w, h=h, x0=x0, k=k,
                                                pool_size=pool_size, do_pool=do_pool, do_w=do_w, theta_init=theta_init,
                                                lambda_init=lambda_init, gamma_init=gamma_init),
        "Rich-ATT": attention.AttentionRichoux(embed_dim=insize, num_heads=num_heads, dropout=dropout),
        "TUnA": attention.TUnA(embed_dim=insize, num_heads=num_heads, dropout=dropout, rffs=rffs, cross=cross, hid_dim=h3)
    }
    return model_mapping[model_name]

def test_predictions(model_name, seed, model, save_confpred):
    test_data = "/nfs/home/students/t.reim/bachelor/pytorchtest/data/gold_stand/gold_stand_val_all_seq.csv"
    emb_name = 'esm2_t33_650'
    layer = 33
    bs = 30
    per_tok_models = ["baseline2d", "dscript_like", "selfattention", "crossattention",
                    "ICAN_cross", "AttDscript", "Rich-ATT", "TUnA"]
    mean_models = ["richoux"]
    padded_models = ["richoux", "TUnA"]
    max = 1000
    # some cases, could be done better or more elegantly
    if model_name in per_tok_models:
        use_embeddings = True
        use_2d_data = True
        emb_type = 'per_tok'
        mean_embedding = False
    elif model_name in mean_models:
        use_embeddings = True
        use_2d_data = False
        emb_type = 'mean'
        mean_embedding = True
    else:
        raise ValueError("The model name does not exist. Please check for spelling errors.")

    embedding_dir = "/nfs/scratch/t.reim/embeddings/" + emb_name + "/" + emb_type + "/"

    if model_name in padded_models:
        use_2d_data = False 

    if use_2d_data:
        vdataset = d.dataset2d(test_data, layer, max, embedding_dir)
    else:
        vdataset = d.MyDataset(test_data, layer, max, use_embeddings, mean_embedding, embedding_dir)

    dataloader = data.DataLoader(vdataset, batch_size=bs, shuffle=True)       

    model = get_model(model, ) #add parameters manually with optimized models

    if torch.cuda.is_available():
        print("Using CUDA")
        model = model.cuda()
        criterion = criterion.cuda()
        device = torch.device("cuda")
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    else:    
        print("Using CPU")
        device = torch.device("cpu")   

    criterion = nn.BCELoss()
    confident_val_predictions = []
    threshold = 0.9   
    model.eval()
    val_loss = 0.0
    tp, fp, tn, fn = 0, 0, 0, 0
    with torch.no_grad():
        for batch in dataloader:

            if use_2d_data:
                val_outputs = model.batch_iterate(batch, device, layer, embedding_dir)
            else:
                val_inputs = batch['tensor'].to(device)
                val_outputs = model(val_inputs)

            if save_confpred:
                names1 = batch['name1']
                names2 = batch['name2']
                output_values = val_outputs.detach().cpu().numpy()
                interactions = torch.round(val_outputs).detach().cpu().numpy()
                labels = batch['interaction'].numpy()

                for value, interaction, label, name1, name2 in zip(output_values, interactions, labels, names1, names2):
                    if value > threshold and interaction == 1 and label == 1:
                        confident_val_predictions.append((name1, name2))
                    
            val_labels = batch['interaction']
            val_labels = val_labels.unsqueeze(1).float()
            predicted_labels = torch.round(val_outputs.float())

            met = confmat(val_labels.to(device), predicted_labels)
            val_loss += criterion(val_outputs, val_labels.to(device))
            tp, fp, tn, fn = tp + met[0], fp + met[1], tn + met[2], fn + met[3]

    avg_loss = val_loss / len(dataloader)
    acc, prec, rec, f1 = metrics(tp, fp, tn, fn)
    print(f'Validation Loss: {avg_loss:.3f}, Accuracy: {acc:.3f}, Precision: {prec:.3f}, Recall: {rec:.3f}, F1: {f1:.3f}')
    print(f'TP: {tp}, FP: {fp}, TN: {tn}, FN: {fn}')


main(dataset='Intra1', model='crossattention')