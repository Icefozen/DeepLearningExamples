#! /usr/bin/python
# -*- coding: utf-8 -*-

# Copyright (c) 2018, NVIDIA CORPORATION. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import time
import tensorflow as tf

import dllogger

__all__ = ['TrainingLoggingHook']


class MeanAccumulator:

    def __init__(self):
        self.sum = 0
        self.count = 0

    def consume(self, value):
        self.sum += value
        self.count += 1

    def value(self):
        return self.sum / self.count


class TrainingLoggingHook(tf.train.SessionRunHook):

    def __init__(self, global_batch_size, num_steps, num_samples, num_epochs, steps_per_epoch, warmup_steps=20):
        self.global_batch_size = global_batch_size
        self.num_steps = num_steps
        self.num_samples = num_samples
        self.num_epochs = num_epochs
        self.steps_per_epoch = steps_per_epoch
        self.warmup_steps = warmup_steps

        self.current_step = 0
        self.current_epoch = 0
        self.t0 = None

        self.mean_throughput = MeanAccumulator()

    # Determines if its the last step of the epoch
    def _last_step_of_epoch(self):
        return self.global_batch_size * (self.current_step + 1) > (self.current_epoch + 1) * self.num_samples

    def before_run(self, run_context):
        run_args = tf.train.SessionRunArgs(
            fetches=[
                tf.train.get_global_step(), 'cross_entropy_loss_ref:0', 'l2_loss_ref:0', 'total_loss_ref:0',
                'learning_rate_ref:0'
            ]
        )
        self.t0 = time.time()

        return run_args

    def after_run(self, run_context, run_values):
        global_step, cross_entropy, l2_loss, total_loss, learning_rate = run_values.results
        batch_time = time.time() - self.t0
        ips = self.global_batch_size / batch_time

        metrics = {
            "imgs_per_sec": ips,
            "cross_entropy": cross_entropy,
            "l2_loss": l2_loss,
            "total_loss": total_loss,
            "learning_rate": learning_rate
        }

        if self.current_step >= self.warmup_steps:
            self.mean_throughput.consume(metrics['imgs_per_sec'])

            metrics = {k: float(v) for k, v in metrics.items()}
            dllogger.log(data=metrics, step=(int(global_step // self.steps_per_epoch), int(global_step)))

        self.current_step += 1

        if self._last_step_of_epoch():
            metrics = {
                "cross_entropy": cross_entropy,
                "l2_loss": l2_loss,
                "total_loss": total_loss,
                "learning_rate": learning_rate
            }
            metrics = {k: float(v) for k, v in metrics.items()}
            dllogger.log(data=metrics, step=(int(global_step // self.steps_per_epoch), ))
            self.current_epoch += 1