# AI Control Agent - Temperature Control System

A reinforcement learning agent that learns to control water temperature by mixing hot and cold water, using only AI (no deterministic control logic).

## Overview

This project demonstrates an AI agent trained with Proximal Policy Optimization (PPO) to control a temperature mixing system. The agent learns optimal control strategies through trial and error, without any pre-programmed control logic.

**Goal**: The agent must achieve a **tank of water at the target temperature with optimal volume** (e.g., 37°C). Success requires both:
- Temperature accuracy (within 0.1°C of target)
- Tank volume in ideal range (80-85% full)

## Features

- **Pure AI Control**: No deterministic PID or rule-based controllers
- **Reinforcement Learning**: Uses Stable-Baselines3 with PPO algorithm
- **Advanced Environment**: 
  - Dump valve for error correction
  - Natural cooling and supply instability
  - Parameter randomization for robust training
  - Volume tracking and energy balance
  - Dual objective: temperature accuracy AND full tank requirement
- **Interactive Testing**: Manual control mode with real-time sliders
- **Checkpoint System**: Resume training from any checkpoint
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

#### Start Training from Scratch

Train a new agent from scratch:
```bash
python train.py
```

Or specify custom number of timesteps:
```bash
python train.py --timesteps 200000
```

This will:
- Train for the specified timesteps (default: 100,000)
- Save checkpoints every 10,000 steps to `./models/checkpoints/`
- Save the best model based on evaluation to `./models/best/`
- Save final model to `./models/ppo_temperature_control_final`
- Log training progress to TensorBoard

#### Continue Training from a Checkpoint

Resume training from a saved checkpoint:
```bash
# Continue from a specific checkpoint
python train.py --checkpoint ./models/checkpoints/ppo_temp_control_80000_steps.zip

# Continue with custom additional timesteps
python train.py --checkpoint ./models/checkpoints/ppo_temp_control_80000_steps.zip --timesteps 50000
# This will train from 80k to 130k total timesteps

# Continue from the best model
python train.py --checkpoint ./models/best/best_model.zip --timesteps 100000

# Continue from final model
python train.py --checkpoint ./models/ppo_temperature_control_final.zip --timesteps 50000
```

**Benefits of resuming:**
- Continue interrupted training sessions
- Fine-tune a good model with more training
- Experiment with different training durations without losing progress
- All training state (weights, timestep counter, etc.) is preserved

#### View Training Progress

View training progress in TensorBoard:
```bash
tensorboard --logdir ./logs/tensorboard/
```

### Understanding Checkpoints

The training process creates several types of saved models:

1. **Periodic Checkpoints** (`./models/checkpoints/`)
   - Saved every 10,000 timesteps
   - Named: `ppo_temp_control_{timesteps}_steps.zip`
   - Use these to resume training or compare performance at different stages

2. **Best Model** (`./models/best/best_model.zip`)
   - Saved whenever evaluation performance improves
   - Evaluated every 5,000 timesteps
   - Usually the most reliable model for testing

3. **Final Model** (`./models/ppo_temperature_control_final.zip`)
   - Saved at the end of training
   - Represents the final trained state after all timesteps

**Example: Compare different checkpoints**
```bash
# Test early training stage
python test_model.py ./models/checkpoints/ppo_temp_control_40000_steps.zip

# Test mid training stage
python test_model.py ./models/checkpoints/ppo_temp_control_80000_steps.zip

# Test best model
python test_model.py ./models/best/best_model.zip

# Test final model
python test_model.py ./models/ppo_temperature_control_final.zip
```

### Backing Up Models

Before retraining with different reward functions or parameters, it's recommended to backup your current models:

```bash
# Backup with custom name
python backup_models.py old_reward_function

# Backup with automatic timestamp
python backup_models.py

# Backup with specific name
python backup_models.py my_backup_name
```

The backup script will:
- Save final and best models to `./models/backup_{name}/`
- Copy all checkpoints to the backup directory
- Preserve models for comparison or restoration

**Restore from backup:**
```bash
cp ./models/backup_old_reward_function/ppo_temperature_control_final.zip ./models/
cp ./models/backup_old_reward_function/best_model.zip ./models/best/
```

**Available Backups:**
- `backup_dump_penalty_100k`: Model trained for 100K timesteps with dump valve penalty
- `backup_150k_timesteps`: Model trained for 150K timesteps with improved temperature control

### Testing a Trained Model

#### Standard Testing Mode

Test and visualize a trained model:
```bash
python test_model.py ./models/best/best_model
```

Or test the final model:
```bash
python test_model.py ./models/ppo_temperature_control_final
```

This will:
- Run 3 test episodes
- Generate visualization plots saved to `control_performance.png`
- Show temperature curves, flow rates, errors, and rewards
- Display volume information and success status for both temperature and volume (80-85% target)

#### Manual Control Mode (Interactive)

Test with interactive controls - adjust parameters in real-time:

**AI Mode with Manual Controls:**
```bash
# AI controls valves, you can adjust supply temps and target via sliders
python test_model.py --manual ./models/best/best_model
```

**Pure Manual Mode (No AI):**
```bash
# You control everything manually via sliders
python test_model.py --manual-only
```

**Custom Parameters:**
```bash
# Set custom initial parameters
python test_model.py --manual ./models/best/best_model \
    --max-steps 600 \
    --target 40.0 \
    --hot-temp 70.0 \
    --cold-temp 8.0 \
    --hot-flow 0.2 \
    --cold-flow 0.1 \
    --dump-flow 0.05
```

**Available Sliders:**
- **Hot Temp**: Hot water supply temperature (0-100°C)
- **Cold Temp**: Cold water supply temperature (0-100°C)
- **Hot Flow**: Hot water flow rate (0 to max)
- **Cold Flow**: Cold water flow rate (0 to max)
- **Dump Flow**: Dump valve flow rate (0 to max)
- **Target Temp**: Target temperature (0-100°C)

**Control Buttons:**
- **Reset**: Reset environment and sliders to initial values
- **AI Mode/Manual Toggle**: Switch between AI control and manual control

**Note:** In AI mode, the agent uses the same environment dynamics as training (with drift enabled). Sliders set base supply temperatures that drift naturally, matching the training conditions.

## Project Structure

```
ai-control-agent/
├── temperature_env.py      # Custom Gymnasium environment
├── train.py                # Training script
├── test_model.py           # Testing and visualization
├── backup_models.py        # Model backup utility
├── requirements.txt        # Python dependencies
├── README.md              # This file
├── models/                # Saved models (created during training)
│   ├── best/             # Best model based on evaluation
│   ├── checkpoints/      # Training checkpoints
│   └── backup_*/         # Model backups (created by backup script)
└── logs/                  # Training logs and TensorBoard data
```

## Environment Details

### State Space (Observation)
- Current temperature (normalized 0-1)
- Target temperature (normalized 0-1) - allows agent to adapt to different targets
- Hot water flow rate (normalized 0-1)
- Cold water flow rate (normalized 0-1)
- Dump valve flow rate (normalized 0-1)
- Normalized time step (0-1)
- Tank volume (normalized 0-1)

### Action Space
- Continuous actions: `[hot_valve_adjustment, cold_valve_adjustment, dump_valve_adjustment]`
- Range: [-1, 1] for each dimension
- Represents change in valve positions (±60% per step)
- Agent can adjust hot, cold, and dump valves independently

### Environment Features
- **Dump Valve**: Allows agent to dump mixed water to correct mistakes
- **Natural Cooling**: Mixed water cools toward ambient temperature (0.01 rate)
- **Supply Instability**: Incoming water temperatures and flows drift during episodes
- **Parameter Randomization**: During training, target temp, initial temp, supply temps, and flow rates are randomized
- **Volume Tracking**: Tank volume changes based on inflows and outflows

### Reward Function
- **Primary**: Negative of temperature error (-1.0 × temp_error)
- **Volume Reward**: 
  - Penalty for being below 80% (-0.5 × volume_error)
  - Progressive bonuses for approaching 80% (70%: +2, 75%: +5)
  - Bonus for being in ideal range 80-85% (+10)
- **Temperature Bonuses**: 
  - Extra reward when close to target (< 0.5°C: +10, < 1.0°C: +5)
- **Volume Penalties**:
  - Penalty for exceeding 85% (-2.0 × excess_volume)
  - **Dump Valve Penalty**: Strong penalty (-5.0 × excess_volume) for not dumping when volume > 85%
- **Combined Success Bonus**: Large bonus (+20) when both temperature is correct (<0.1°C) AND volume is in ideal range (80-85%)
- **Penalties**: 
  - Small penalty for excessive flow (energy efficiency: -0.01 per unit flow)
  - Discourage unnecessary dumping (-0.1 per unit dump flow)
  - Additional penalty for dumping when temperature is close to target
- **Valve Efficiency**: Rewards/penalties for efficient hot/cold water usage based on temperature needs

### Termination
- **Success**: Requires BOTH conditions:
  - Temperature within 0.1°C of target
  - Tank volume in ideal range (80-85% full)
- **Timeout**: Maximum steps (600) reached

**Note**: The agent must achieve both temperature accuracy AND optimal volume (80-85%) to succeed. The dump valve penalty encourages the agent to actively reduce volume when overfilled, teaching it to stop at the target range rather than filling to 100%.

## Customization

### Adjust Environment Parameters
Edit `temperature_env.py` or pass parameters:
```python
env = TemperatureControlEnv(
    target_temp=40.0,              # Target temperature
    initial_temp=20.0,               # Starting temperature
    hot_water_temp=60.0,            # Hot supply temperature
    cold_water_temp=10.0,           # Cold supply temperature
    max_flow_rate=1.0,              # Maximum flow rate
    max_dump_flow_rate=1.0,         # Maximum dump flow rate
    mixed_water_cooling_rate=0.01,  # Cooling rate toward ambient
    max_steps=600,                  # Maximum episode length
    randomize_params=True            # Enable parameter randomization
)
```

### Modify Training Parameters
Edit `train.py` or use command-line arguments:
- `--timesteps`: Number of timesteps to train (default: 100,000)
- `--checkpoint`: Path to checkpoint to resume from
- `learning_rate`: Learning rate (in code: 3e-4)
- `n_steps`: Steps per update (in code: 2048)
- `batch_size`: Batch size for updates (in code: 64)
- `n_epochs`: Number of epochs per update (in code: 10)

### Adjust Checkpoint Frequency
Edit `train.py`:
```python
checkpoint_callback = CheckpointCallback(
    save_freq=5000,  # Save every 5k steps (default: 10k)
    save_path="./models/checkpoints/",
    name_prefix="ppo_temp_control"
)
```

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

