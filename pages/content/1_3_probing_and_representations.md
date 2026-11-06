# Probing and Representations

This section explores how language models represent and use information internally. You'll learn techniques for probing model internals, understanding how features are represented, and how to steer model behaviour.

## What You'll Learn

- **Linear Probing**: Train simple classifiers to detect concepts in model activations, and use this to understand what models "know" at different layers
- **Function Vectors**: Discover how models encode task-specific behaviour, and extract vectors that can transfer behaviour between contexts
- **SAE-based Interpretability**: Use Sparse Autoencoders to decompose model activations into interpretable features, and explore tools like SAELens and Neuronpedia
- **Activation Oracles**: Query a model's activations with open-ended natural-language questions, using an LLM trained to read another model's internals

## Sections

The exercises in this section are:

- **1.3.1 Linear Probes**: Train linear probes to find truth representations, check causally that the model uses them, then apply probes to deception detection and high-stakes requests
- **1.3.2 Function Vectors & Model Steering**: Extract and apply function vectors to steer model outputs
- **1.3.3 Interpretability with SAEs**: Hands-on exploration of sparse autoencoders for finding interpretable features
- **1.3.4 Activation Oracles**: Explore and understand activation oracles for recovering information from model internals

## Prerequisites

You should have completed sections 1.1 and 1.2 before starting this material.
