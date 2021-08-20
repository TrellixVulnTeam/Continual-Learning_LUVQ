# -*- coding: utf-8 -*-
"""
Copyright 2021 Christopher Francis Angelini

"""

import torch
import torch.nn as nn
import torch.utils.data
from Comps.VDP_Layers import VDP_Flatten, VDP_Conv2D, VDP_Relu, VDP_Maxpool, VDP_FullyConnected, VDP_Softmax
from utils import conv_weight_args, fc_weight_args


class Net(nn.Module):
    def __init__(self, args):
        super(Net, self).__init__()

        # Hypers
        self.tau = args.tau
        self.clamp = args.clamp
        self.var_sup = args.var_sup

        self.conv_init = conv_weight_args(args)
        self.fc_init = fc_weight_args(args)

        # self.conv2d1 = VDP_Conv2D(1, 32, 3, input_flag=True, weight_args=self.conv_init)
        self.conv2d1 = VDP_Conv2D(1, 64, 3, input_flag=True, weight_args=self.conv_init)

        # self.conv2d2 = VDP_Conv2D(32, 64, 5, weight_args=self.conv_init)
        self.conv2d2 = VDP_Conv2D(64, 128, 3, weight_args=self.conv_init)
        self.conv2d3 = VDP_Conv2D(128, 256, 3, weight_args=self.conv_init)

        self.relu = VDP_Relu()
        self.maxpool = VDP_Maxpool(2, 2)
        self.theflattening = VDP_Flatten()
        #args.ways added for few shot
        # self.fullyCon1 = VDP_FullyConnected(1024, args.ways, weight_args=self.fc_init)
        self.fullyCon1 = VDP_FullyConnected(2304, 128, weight_args=self.fc_init)
        self.fullyCon2 = VDP_FullyConnected(128, args.ways, weight_args=self.fc_init)
        self.softmax = VDP_Softmax(1)

    def forward(self, x_input):
        # Input Dim: (1, 28, 28)
        # [(W−K+2P)/S]+1
        mu, sigma = self.conv2d1.forward(x_input)
        mu, sigma = self.relu.forward(mu, sigma)
        # print("C1:", mu.size())
        # (32, 26, 26)
        mu, sigma = self.maxpool.forward(mu, sigma)
        # (32, 13, 13)

        mu, sigma = self.conv2d2.forward(mu, sigma)
        mu, sigma = self.relu.forward(mu, sigma)
        # print("C2:", mu.size())
        # (64, 13, 13)
        mu, sigma = self.maxpool.forward(mu, sigma)
        # (64, 6, 6)
        mu, sigma = self.conv2d3.forward(mu, sigma)
        # print("C3:", mu.size())
        # (256, 3, 3)
        mu, sigma = self.relu.forward(mu, sigma)
        # mu, sigma = self.maxpool.forward(mu, sigma)

        mu_flat, sigma_flat = self.theflattening.forward(mu, sigma)
        mu, sigma = self.fullyCon1.forward(mu_flat, sigma_flat)
        # print("FC1:", mu.size())
        mu, sigma = self.fullyCon2.forward(mu, sigma)
        # print("FC2:", mu.size())
        mu, sigma = self.softmax.forward(mu, sigma)

        return mu, sigma

    def nll_gaussian(self, y_pred_mean, y_pred_sd, y_test):
        thing = torch.diag(torch.ones(list(self.children())[-2].out_features, device=y_pred_sd.device) * torch.tensor(self.var_sup, device=y_pred_sd.device))
        y_pred_sd_inv = torch.inverse(y_pred_sd + thing)
        mu_ = y_pred_mean - y_test
        mu_sigma = torch.bmm(mu_.unsqueeze(1), y_pred_sd_inv)
        ms = 0.5 * torch.bmm(mu_sigma, mu_.unsqueeze(2)).squeeze(1) + 0.5 * torch.log(torch.det(y_pred_sd + thing)).unsqueeze(1)
        ms = ms.mean()
        return ms

    def batch_loss(self, output_mean, output_sigma, label):
        output_sigma_clamp = torch.clamp(output_sigma, -self.clamp, self.clamp)
        neg_log_likelihood = self.nll_gaussian(output_mean, output_sigma_clamp, label)
        loss_value = neg_log_likelihood + (self.tau * self.conv2d1.kl_loss_term() +
                                           self.tau * self.conv2d2.kl_loss_term() +
                                           self.tau * self.fullyCon1.kl_loss_term())
        return loss_value
