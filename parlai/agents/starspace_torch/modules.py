#!/usr/bin/env python3

# Copyright (c) 2017-present, Facebook, Inc.
# All rights reserved.
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

import math
import torch
import torch.nn as nn


class Starspace(nn.Module):
    def __init__(self, opt, num_features, dict):
        super().__init__()
        self.opt = opt

        # set up encoder
        self.lt = nn.Embedding(num_features, opt['embeddingsize'], 0,
                               sparse=True, max_norm=opt['embeddingnorm'])
        self.encoder = Encoder(self.lt, dict)
        if not opt['tfidf']:
            dict = None
        if not opt['share_embeddings']:
            self.lt2 = nn.Embedding(num_features, opt['embeddingsize'], 0,
                                    sparse=True, max_norm=opt['embeddingnorm'])
            self.encoder2 = Encoder(self.lt2, dict)
        else:
            self.encoder2 = self.encoder

        # set up linear layer(s)
        self.lin = nn.Linear(opt['embeddingsize'], opt['embeddingsize'], bias=False)
        self.lins = opt.get('lins', 0)

    def forward(self, xs, ys=None, cands=None):
        xs_emb = self.encoder(xs)
        if self.lins > 0:
            xs_emb = self.lin(xs_emb)
        ys_emb = None
        if ys is not None:
            # training includes the correct example first.
            ys_emb = self.encoder2(ys)
        if cands is not None:
            bsz = cands.size(0)
            cands = cands.view(-1, cands.size(-1))
            cands_emb = self.encoder2(cands)
            cands_emb = cands_emb.view(bsz, -1, cands_emb.size(-1))
            if ys_emb is not None:
                # during training, we have the correct answer first
                ys_emb = ys_emb.unsqueeze(1)
                ys_emb = torch.cat([ys_emb, cands_emb], dim=1)
            else:
                ys_emb = cands_emb
        return xs_emb, ys_emb


class Encoder(nn.Module):
    def __init__(self, shared_lt, dict):
        super().__init__()
        self.lt = shared_lt
        if dict is not None:
            num_words = len(dict)
            freqs = torch.Tensor(num_words)
            for i in range(num_words):
                ind = dict.ind2tok[i]
                freq = dict.freq[ind]
                freqs[i] = 1.0 / (1.0 + math.log(1.0 + freq))
            self.freqs = freqs
        else:
            self.freqs = None

    def forward(self, xs):
        xs_emb = self.lt(xs)
        if self.freqs is not None:
            # tfidf embeddings
            bsz = xs.size(0)
            len_x = xs.size(1)
            x_scale = torch.Tensor(bsz, len_x)
            for i in range(len_x):
                for j in range(bsz):
                    x_scale[j][i] = self.freqs[xs.data[j][i]]
            x_scale = x_scale.mul(1 / x_scale.norm())
            if xs_emb.is_cuda:
                x_scale = x_scale.cuda()
            xs_emb = xs_emb.transpose(1, 2).matmul(x_scale.unsqueeze(-1)).squeeze(-1)
        else:
            # basic embeddings (faster)
            xs_emb = xs_emb.mean(1)
        return xs_emb
