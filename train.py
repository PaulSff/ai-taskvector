"""
Training script for the temperature control AI agent.
Uses Stable-Baselines3 with PPO algorithm.
"""
import os
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import EvalCallback, CheckpointCallback
from stable_baselines3.common.env_util import make_vec_env
from temperature_env import TemperatureControlEnv


def main():
    # Create environment
    print("Creating environment...")
    env = TemperatureControlEnv(
        target_temp=37.0,
        initial_temp=20.0,
        hot_water_temp=60.0,
        cold_water_temp=10.0,
        max_flow_rate=1.0,
        max_dump_flow_rate=1.0,
        mixed_water_cooling_rate=0.01,
        max_steps=600,
        randomize_params=True
    )
    
    # Create vectorized environment for faster training
    # Using 4 parallel environments
    vec_env = make_vec_env(
        TemperatureControlEnv,
        n_envs=4,
        env_kwargs={
            "target_temp": 37.0,
            "initial_temp": 20.0,
            "hot_water_temp": 60.0,
            "cold_water_temp": 10.0,
            "max_flow_rate": 1.0,
            "max_dump_flow_rate": 1.0,
            "mixed_water_cooling_rate": 0.01,
            "max_steps": 600,
            "randomize_params": True
        }
    )
    
    # Create evaluation environment
    eval_env = TemperatureControlEnv(
        target_temp=37.0,
        initial_temp=20.0,
        hot_water_temp=60.0,
        cold_water_temp=10.0,
        max_flow_rate=1.0,
        max_dump_flow_rate=1.0,
        mixed_water_cooling_rate=0.01,
        max_steps=600
    )
    
    # Create model directory
    os.makedirs("models", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    
    # Initialize PPO agent
    print("Initializing PPO agent...")
    model = PPO(
        "MlpPolicy",
        vec_env,
        learning_rate=3e-4,
        n_steps=2048,
        batch_size=64,
        n_epochs=10,
        gamma=0.99,
        gae_lambda=0.95,
        clip_range=0.2,
        ent_coef=0.01,  # Encourage exploration
        verbose=1,
        tensorboard_log="./logs/tensorboard/"
    )
    
    # Setup callbacks
    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path="./models/best/",
        log_path="./logs/eval/",
        eval_freq=5000,
        deterministic=True,
        render=False
    )
    
    checkpoint_callback = CheckpointCallback(
        save_freq=10000,
        save_path="./models/checkpoints/",
        name_prefix="ppo_temp_control"
    )
    
    # Train the agent
    print("Starting training...")
    print("Training will run for 100,000 timesteps.")
    print("Check TensorBoard logs at: ./logs/tensorboard/")
    
    model.learn(
        total_timesteps=100000,
        callback=[eval_callback, checkpoint_callback],
        progress_bar=True
    )
    
    # Save final model
    model.save("./models/ppo_temperature_control_final")
    print("\nTraining complete! Model saved to ./models/ppo_temperature_control_final")
    
    # Test the trained model
    print("\nTesting trained model...")
    test_episode(eval_env, model, num_episodes=5)


def test_episode(env, model, num_episodes=1):
    """Test the trained model on a few episodes."""
    for episode in range(num_episodes):
        obs, info = env.reset()
        done = False
        total_reward = 0
        steps = 0
        
        print(f"\n=== Episode {episode + 1} ===")
        
        while not done:
            action, _states = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated
            total_reward += reward
            steps += 1
            
            if steps % 10 == 0:
                env.render()
        
        print(f"Episode finished after {steps} steps")
        print(f"Final temperature: {info['temperature']:.2f}°C")
        print(f"Target temperature: {env.target_temp}°C")
        print(f"Error: {abs(info['temperature'] - env.target_temp):.2f}°C")
        print(f"Total reward: {total_reward:.2f}")


if __name__ == "__main__":
    main()

