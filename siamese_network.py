#!/usr/bin/env python
# encoding=utf-8
'''
@Time    :   2020/10/17 11:38:00
@Author  :   zhiyang.zzy 
@Contact :   zhiyangchou@gmail.com
@Desc    :   1. 使用预训练词向量。2. 使用lcqmc数据集实验，
'''

# here put the import lib
import imp
from os import name
import time
import numpy as np
import tensorflow as tf
import random
import paddlehub as hub
from tqdm import tqdm
import math
from sklearn.metrics import accuracy_score
import os

import data_input
from config import Config


random.seed(9102)

start = time.time()

# 读取配置
conf = Config()
os.environ["CUDA_VISIBLE_DEVICES"] = "4"
# 读取数据
dataset = hub.dataset.LCQMC()
data_train, data_val, data_test = data_input.get_lcqmc()
# data_train = data_train[:100]
print("train size:{},val size:{}, test size:{}".format(
    len(data_train), len(data_val), len(data_test)))


def variable_summaries(var, name):
    """Attach a lot of summaries to a Tensor."""
    with tf.name_scope('summaries'):
        mean = tf.reduce_mean(var)
        tf.summary.scalar('mean/' + name, mean)
        with tf.name_scope('stddev'):
            stddev = tf.sqrt(tf.reduce_sum(tf.square(var - mean)))
        tf.summary.scalar('sttdev/' + name, stddev)
        tf.summary.scalar('max/' + name, tf.reduce_max(var))
        tf.summary.scalar('min/' + name, tf.reduce_min(var))
        tf.summary.histogram(name, var)


with tf.name_scope('input'):
    # 预测时只用输入query即可，将其embedding为向量。
    query_batch = tf.placeholder(
        tf.int32, shape=[None, None], name='query_batch')
    doc_batch = tf.placeholder(tf.int32, shape=[None, None], name='doc_batch')
    query_seq_length = tf.placeholder(
        tf.int32, shape=[None], name='query_sequence_length')
    doc_seq_length = tf.placeholder(
        tf.int32, shape=[None], name='doc_seq_length')
    # label
    sim_labels = tf.placeholder(tf.float32, shape=[None], name="sim_labels")
    keep_prob_place = tf.placeholder(tf.float32, name='keep_prob')


with tf.name_scope('word_embeddings_layer'):
    # 这里可以加载预训练词向量
    _word_embedding = tf.get_variable(name="word_embedding_arr", dtype=tf.float32,
                                      shape=[conf.nwords, conf.word_dim])
    query_embed = tf.nn.embedding_lookup(
        _word_embedding, query_batch, name='query_batch_embed')
    doc_embed = tf.nn.embedding_lookup(
        _word_embedding, doc_batch, name='doc_positive_embed')

with tf.name_scope('RNN'):
    # Abandon bag of words, use GRU, you can use stacked gru
    # query_l1 = add_layer(query_batch, conf.word_dim, L1_N, activation_function=None)  # tf.nn.relu()
    # doc_positive_l1 = add_layer(doc_positive_batch, conf.word_dim, L1_N, activation_function=None)
    # doc_negative_l1 = add_layer(doc_negative_batch, conf.word_dim, L1_N, activation_function=None)
    if conf.use_stack_rnn:
        cell_fw = tf.contrib.rnn.GRUCell(
            conf.hidden_size_rnn, reuse=tf.AUTO_REUSE)
        stacked_gru_fw = tf.contrib.rnn.MultiRNNCell(
            [cell_fw], state_is_tuple=True)
        cell_bw = tf.contrib.rnn.GRUCell(
            conf.hidden_size_rnn, reuse=tf.AUTO_REUSE)
        stacked_gru_bw = tf.contrib.rnn.MultiRNNCell(
            [cell_fw], state_is_tuple=True)
        (output_fw, output_bw), (_, _) = tf.nn.bidirectional_dynamic_rnn(
            stacked_gru_fw, stacked_gru_bw)
        # not ready, to be continue ...
    else:
        cell_fw = tf.contrib.rnn.GRUCell(
            conf.hidden_size_rnn, reuse=tf.AUTO_REUSE)
        cell_bw = tf.contrib.rnn.GRUCell(
            conf.hidden_size_rnn, reuse=tf.AUTO_REUSE)
        # query
        (_, _), (query_output_fw, query_output_bw) = tf.nn.bidirectional_dynamic_rnn(cell_fw, cell_bw, query_embed,
                                                                                     sequence_length=query_seq_length,
                                                                                     dtype=tf.float32)
        query_rnn_output = tf.concat(
            [query_output_fw, query_output_bw], axis=-1)
        query_rnn_output = tf.nn.dropout(query_rnn_output, keep_prob_place)
        # doc_pos
        (_, _), (doc_output_fw, doc_output_bw) = tf.nn.bidirectional_dynamic_rnn(cell_fw, cell_bw,
                                                                                 doc_embed,
                                                                                 sequence_length=doc_seq_length,
                                                                                 dtype=tf.float32)
        doc_rnn_output = tf.concat([doc_output_fw, doc_output_bw], axis=-1)
        doc_rnn_output = tf.nn.dropout(doc_rnn_output, keep_prob_place)

with tf.name_scope('Cosine_Similarity'):
    # Cosine similarity
    # query_norm = sqrt(sum(each x^2))
    query_norm = tf.sqrt(tf.reduce_sum(tf.square(query_rnn_output), 1))
    # doc_norm = sqrt(sum(each x^2))
    doc_norm = tf.sqrt(tf.reduce_sum(tf.square(doc_rnn_output), 1))

    # 内积
    prod = tf.multiply(query_norm, doc_norm)
    # prod = tf.reduce_sum(tmp, 1)

    # cos_sim_raw = query * doc / (||query|| * ||doc||)
    cos_sim_raw = tf.truediv(prod, tf.multiply(query_norm, doc_norm))
    predict_prob = tf.sigmoid(cos_sim_raw)
    predict_idx = tf.cast(tf.greater_equal(predict_prob, 0.5), tf.int32)

with tf.name_scope('Loss'):
    # Train Loss
    loss = tf.nn.sigmoid_cross_entropy_with_logits(
        labels=sim_labels, logits=cos_sim_raw)
    loss = tf.reduce_mean(loss)
    tf.summary.scalar('loss', loss)

with tf.name_scope('Training'):
    # Optimizer
    train_step = tf.train.AdamOptimizer(conf.learning_rate).minimize(loss)

# with tf.name_scope('Accuracy'):
#     correct_prediction = tf.equal(tf.argmax(prob, 1), 0)
#     accuracy = tf.reduce_mean(tf.cast(correct_prediction, tf.float32))
#     tf.summary.scalar('accuracy', accuracy)

merged = tf.summary.merge_all()

with tf.name_scope('Test'):
    average_loss = tf.placeholder(tf.float32)
    loss_summary = tf.summary.scalar('average_loss', average_loss)

with tf.name_scope('Train'):
    train_average_loss = tf.placeholder(tf.float32)
    train_loss_summary = tf.summary.scalar(
        'train_batch_loss', train_average_loss)


def feed_batch(t1_ids, t1_len, t2_ids, t2_len, label=None, is_test=0):
    keep_porb = 1 if is_test else conf.keep_porb
    fd = {
        query_batch: t1_ids, doc_batch: t2_ids, query_seq_length: t1_len,
        doc_seq_length: t2_len, keep_prob_place: keep_porb}
    if label:
        fd[sim_labels] = label
    return fd


def eval(sess, test_data):
    pbar = tqdm(data_input.get_batch(
        test_data, batch_size=conf.batch_size, is_test=1))
    val_label, val_pred = [], []
    for (t1_ids, t1_len, t2_ids, t2_len, label) in pbar:
        val_label.extend(label)
        fd = feed_batch(t1_ids, t1_len, t2_ids, t2_len, is_test=1)
        pred_labels = sess.run(predict_idx, feed_dict=fd)
        val_pred.extend(pred_labels)
    test_acc = accuracy_score(val_label, val_pred)
    print("dev set acc:", test_acc)
    return test_acc

# config = tf.ConfigProto()  # log_device_placement=True)
# config.gpu_options.allow_growth = True
# if not config.gpu:
# config = tf.ConfigProto(device_count= {'GPU' : 0})


# 创建一个Saver对象，选择性保存变量或者模型。
saver = tf.train.Saver()
# with tf.Session(config=config) as sess:
with tf.Session() as sess:
    sess.run(tf.global_variables_initializer())
    train_writer = tf.summary.FileWriter(
        conf.summaries_dir + '/train', sess.graph)
    start = time.time()
    for epoch in range(conf.num_epoch):
        steps = int(math.ceil(float(len(data_train)) / conf.batch_size))
        # 每个 epoch 分batch训练
        pbar = tqdm(data_input.get_batch(
            data_train, batch_size=conf.batch_size))
        for i, (t1_ids, t1_len, t2_ids, t2_len, label) in enumerate(pbar):
            fd = feed_batch(t1_ids, t1_len, t2_ids, t2_len, label)
            # s = sess.run([query_norm, doc_norm, prod], feed_dict=fd)
            _, cur_loss = sess.run([train_step, loss], feed_dict=fd)
            pbar.set_description("Train loss:{};".format(cur_loss))
            # train_loss = sess.run(train_loss_summary, feed_dict={train_average_loss: cur_loss})
            # train_writer.add_summary(cur_loss, epoch * steps + i + 1)
        # 训练完一个epoch之后，使用验证集评估，然后预测， 然后评估准确率
        dev_acc = eval(sess, data_val)

    # test 模型的准确率
    test_acc = eval(sess, data_test)
    print("dev set acc:", test_acc)
    # 保存模型
    save_path = saver.save(sess, "model/model_1.ckpt")
    print("Model saved in file: ", save_path)
