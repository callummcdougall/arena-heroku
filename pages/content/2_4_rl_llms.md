# RL + LLMs

In this section you'll use reinforcement learning to fine-tune language models, the way current
LLM post-training does. Each part uses a different source of reward: a reward model standing in for
human preferences (RLHF), a programmatic verifier that checks the answer (RLVR), and another LLM acting
as a judge (RLAIF). All three use GRPO-style algorithms, which estimate the advantage from a group of
rollouts for the same prompt instead of training a critic.

## What You'll Learn

- **2.4.1 RLHF**: Map states, actions and rewards onto autoregressive generation, build GRPO up piece by piece (sampling, rewards, advantages, the clipped objective) into a `GRPO_Trainer`, then implement LoRA from scratch to RL fine-tune a model too big to train in full on a single GPU
- **2.4.2 RLVR**: Train `Qwen3-0.6B-Base` on multi-digit multiplication with a verifiable reward and Dr. GRPO, keep problems near a 50% solve rate with a difficulty controller, and investigate whether RL teaches new capabilities or elicits ones the base model already had
- **2.4.3 RLAIF**: Train a small model against a frozen LLM judge, watch it learn the task and then learn to fool the judge, and try defences against this reward hacking

## Prerequisites

- You should be comfortable with the policy gradient theorem from Section 2.2.2 (VPG). You don't need to have done Section 2.3 (PPO), although if you have, you'll recognise the clipped surrogate objective.
- We recommend doing the parts in order: 2.4.2 builds on the GRPO trainer and LoRA from 2.4.1, and 2.4.3 reuses the multiplication task from 2.4.2.
- These exercises need a GPU. 2.4.1 expects at least 24GB of memory, but switches to smaller models automatically on smaller GPUs.
