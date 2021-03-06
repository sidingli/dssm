#!/usr/bin/env python
#encoding=utf-8
'''
@Time    :   2020/10/25 22:28:30
@Author  :   zhiyang.zzy 
@Contact :   zhiyangchou@gmail.com
@Desc    :   
'''

# here put the import lib
import imp
import os
import time
from numpy.lib.arraypad import pad
from tensorflow.python.ops.gen_io_ops import write_file
import yaml
import logging
import argparse
logging.basicConfig(level=logging.INFO)
import data_input
from config import Config
from model.siamese_network import SiamenseRNN, SiamenseBert
from data_input import Vocabulary, get_test
from util import write_file

def train_siamese():
    # 读取配置
    # conf = Config()
    cfg_path = "./configs/config.yml"
    cfg = yaml.load(open(cfg_path, encoding='utf-8'), Loader=yaml.FullLoader)
    os.environ["CUDA_VISIBLE_DEVICES"] = "4"
    # 读取数据
    data_train, data_val, data_test = data_input.get_lcqmc()
    # data_train = data_train[:10000]
    print("train size:{},val size:{}, test size:{}".format(
        len(data_train), len(data_val), len(data_test)))
    model = SiamenseRNN(cfg)
    model.fit(data_train, data_val, data_test)
    pass

def predict_siamese(file_='./results/'):
    # 加载配置
    cfg_path = "./configs/config.yml"
    cfg = yaml.load(open(cfg_path, encoding='utf-8'), Loader=yaml.FullLoader)
    os.environ["CUDA_VISIBLE_DEVICES"] = "4"
    # 将 seq转为id，
    vocab = Vocabulary(meta_file='./data/vocab.txt', max_len=cfg['max_seq_len'], allow_unk=1, unk='[UNK]', pad='[PAD]')
    test_arr, query_arr = get_test(file_, vocab)
    # 加载模型
    model = SiamenseRNN(cfg)
    model.restore_session(cfg["checkpoint_dir"])
    test_label, test_prob = model.predict(test_arr)
    out_arr = [x + [test_label[i]] + [test_prob[i]] for i, x in enumerate(query_arr)]
    write_file(out_arr, file_ + '.siamese.predict', )
    pass

def train_siamese_bert():
    # 读取配置
    # conf = Config()
    cfg_path = "./configs/config_bert.yml"
    cfg = yaml.load(open(cfg_path, encoding='utf-8'), Loader=yaml.FullLoader)
    os.environ["CUDA_VISIBLE_DEVICES"] = "4"
    # vocab: 将 seq转为id，
    vocab = Vocabulary(meta_file='./data/vocab.txt', max_len=cfg['max_seq_len'], allow_unk=1, unk='[UNK]', pad='[PAD]')
    # 读取数据
    data_train, data_val, data_test = data_input.get_lcqmc_bert(vocab)
    # data_train = data_train[:1000]
    print("train size:{},val size:{}, test size:{}".format(
        len(data_train), len(data_val), len(data_test)))
    model = SiamenseBert(cfg)
    model.fit(data_train, data_val, data_test)
    pass

if __name__ == "__main__":
    os.environ["CUDA_VISIBLE_DEVICES"] = "4"
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", default="rnn", type=str, help="train/predict")
    ap.add_argument("--mode", default="train", type=str, help="train/predict")
    ap.add_argument("--file", default="./results/input/test", type=str, help="train/predict")
    args = ap.parse_args()
    if args.mode == 'train' and args.method == 'rnn':
        train_siamese()
    elif args.mode == 'predict' and args.method == 'rnn':
        predict_siamese(args.file)
    elif args.mode == 'train' and args.method == 'bert':
        train_siamese_bert()
