# AI Control Agent - Temperature Control System

A reinforcement learning agent that learns to control water temperature by mixing hot and cold water, using only AI (no deterministic control logic).

## Overview

This project demonstrates an AI agent trained with Proximal Policy Optimization (PPO) to control a temperature mixing system. The agent learns optimal control strategies through trial and error, without any pre-programmed control logic.

## Features

- **Pure AI Control**: No deterministic PID or rule-based controllers
- **Reinforcement Learning**: Uses Stable-Baselines3 with PPO algorithm
- **Simulation Environment**: Custom Gymnasium environment for temperature control
- **Visualization**: Tools to visualize agent performance
- **Extensible**: Easy to adapt for other control tasks

## Installation

1. Create a virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Training the Agent

Train a new agent from scratch:
```bash
python train.py
```

This will:
- Train for 100,000 timesteps
- Save checkpoints every 10,000 steps
- Save the best model based on evaluation
- Log training progress to TensorBoard

View training progress:
```bash
tensorboard --logdir ./logs/tensorboard/
```

### Testing a Trained Model

Test and visualize a trained model:
```bash
python test_model.py models/best/best_model
```

Or test the final model:
```bash
python test_model.py models/ppo_temperature_control_final
```

## Project Structure

```
ai-control-agent/
├── temperature_env.py      # Custom Gymnasium environment
├── train.py                # Training script
├── test_model.py           # Testing and visualization
├── requirements.txt        # Python dependencies
├── README.md              # This file
├── models/                # Saved models (created during training)
│   ├── best/             # Best model based on evaluation
│   └── checkpoints/      # Training checkpoints
└── logs/                  # Training logs and TensorBoard data
```

## Environment Details

### State Space
- Current temperature (normalized)
- Hot water flow rate (normalized)
- Cold water flow rate (normalized)
- Normalized time step

### Action Space
- Continuous actions: `[hot_valve_adjustment, cold_valve_adjustment]`
- Range: [-1, 1] for each dimension
- Represents change in valve positions

### Reward Function
- Primary: Negative of temperature error
- Bonus: Extra reward when close to target (< 0.5°C or < 1.0°C)
- Penalty: Small penalty for excessive flow (energy efficiency)

### Termination
- Success: Temperature within 0.1°C of target
- Timeout: Maximum steps (200) reached

## Customization

### Adjust Target Temperature
Edit `temperature_env.py` or pass parameters:
```python
env = TemperatureControlEnv(target_temp=40.0)  # Change target
```

### Modify Training Parameters
Edit `train.py`:
- `total_timesteps`: Training duration
- `learning_rate`: Learning rate
- `n_steps`: Steps per update
- `batch_size`: Batch size for updates

### Adapt for Other Control Tasks
1. Modify `TemperatureControlEnv` in `temperature_env.py`
2. Adjust state/action spaces
3. Update physics model in `step()` method
4. Customize reward function

## Real-World Deployment

To deploy on real hardware:

1. **Safety First**: Add hard limits and emergency stops
2. **Interface**: Replace simulation with hardware interface
3. **Fine-tuning**: Use transfer learning or fine-tune on real data
4. **Monitoring**: Add logging and monitoring systems
5. **Gradual Deployment**: Start with conservative exploration

Example hardware interface:
```python
class RealHardwareEnv(TemperatureControlEnv):
    def step(self, action):
        # Send action to actual valves/actuators
        # Read real temperature sensor
        # Return observation and reward
```

## Interactive Chat Interfaces

### Rule-Based Chat (No Setup Required)
```bash
python chat_with_model.py
```
Simple natural language interface using keyword matching.

### Local AI Chat (Ollama - Recommended)
Uses a local LLM running on your machine - no API keys needed!

**Setup:**
1. Install Ollama: https://ollama.ai
2. Pull a model (choose one):
   ```bash
   ollama pull llama3.2        # Fast, efficient (recommended)
   ollama pull mistral          # Alternative option
   ollama pull llama3.1         # Larger, more capable
   ```
3. Start Ollama service (usually runs automatically)
4. Run the chat:
   ```bash
   python chat_with_local_ai.py
   ```

**Usage:**
```bash
# Use default model (llama3.2)
python chat_with_local_ai.py

# Use a different model
python chat_with_local_ai.py --model mistral

# List available models
python chat_with_local_ai.py --list-models
```

### Cloud AI Chat (OpenAI - Optional)
For cloud-based AI chat, see `chat_with_ai.py`. Requires OpenAI API key.

## Next Steps

- [ ] Add more sophisticated physics modeling
- [ ] Implement different RL algorithms (SAC, TD3)
- [ ] Add noise and disturbance modeling
- [ ] Create multi-objective optimization (temperature + efficiency)
- [ ] Implement transfer learning for different target temperatures
- [ ] Add safety constraints and emergency protocols

## Resources

- [Stable-Baselines3 Documentation](https://stable-baselines3.readthedocs.io/)
- [Gymnasium Documentation](https://gymnasium.farama.org/)
- [PPO Paper](https://arxiv.org/abs/1707.06347)

## License

MIT License - feel free to use and modify for your projects!

