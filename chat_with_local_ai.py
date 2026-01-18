"""
Local AI-powered chat interface for the trained temperature control model.
Uses Ollama (local LLM) for natural conversation - no API keys needed!
"""
import sys
import os
import re
import json
from stable_baselines3 import PPO
from temperature_env import TemperatureControlEnv

# Try to import ollama, but make it optional
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    print("⚠️  Ollama not installed. Install with: pip install ollama")
    print("   Also make sure Ollama is running: https://ollama.ai")


class LocalAIChat:
    def __init__(self, model_path="models/best/best_model", model_name="llama3.2"):
        """Initialize the local AI chat interface."""
        print("🤖 Loading AI temperature control agent...")
        try:
            self.model = PPO.load(model_path)
            print("✅ Control model loaded successfully!")
        except Exception as e:
            print(f"❌ Error loading model: {e}")
            sys.exit(1)
        
        # Check if Ollama is available
        self.use_ai = OLLAMA_AVAILABLE
        self.model_name = model_name
        
        if self.use_ai:
            try:
                # Test if Ollama is running
                ollama.list()
                print(f"✅ Local AI chat enabled (using {model_name})")
                self.ollama_client = ollama
            except Exception as e:
                print(f"⚠️  Ollama not running or {model_name} not available.")
                print(f"   Error: {e}")
                print("   Make sure Ollama is installed and running:")
                print("   1. Install: https://ollama.ai")
                print(f"   2. Pull model: ollama pull {model_name}")
                print("   3. Start Ollama service")
                print("   Falling back to rule-based chat...")
                self.use_ai = False
        else:
            print("ℹ️  Using rule-based chat (install ollama for AI chat)")
        
        # System parameters
        self.target_temp = 37.0
        self.initial_temp = 20.0
        self.hot_water_temp = 60.0
        self.cold_water_temp = 10.0
        self.max_flow_rate = 1.0
        self.max_steps = 200
        
        self.env = None
        self._create_env()
        
        # Conversation history for context
        self.conversation_history = []
        self._initialize_conversation()
    
    def _initialize_conversation(self):
        """Initialize conversation with system prompt."""
        system_prompt = """You are a helpful AI assistant that controls a water temperature system. 
You can mix hot and cold water to reach target temperatures. 

Your capabilities:
- Set target temperature (user says things like "I want 40 degrees" or "heat to 45°C")
- Set initial/starting temperature (user says "start from 25" or "begin at 30°C")
- Run temperature control tests (user says "run a test", "try it", "show me", "go")
- Check current status (user says "what's the status", "current settings")
- Adjust hot/cold water temperatures if needed

When the user wants to set parameters, extract the values and confirm. When they want to run a test, 
acknowledge and prepare to run it. Be friendly, conversational, and helpful.

Current system state will be provided in your context. Always confirm changes before applying them.
Keep responses concise and friendly."""
        
        self.conversation_history = [
            {"role": "system", "content": system_prompt}
        ]
    
    def _create_env(self):
        """Create or recreate the environment."""
        self.env = TemperatureControlEnv(
            target_temp=self.target_temp,
            initial_temp=self.initial_temp,
            hot_water_temp=self.hot_water_temp,
            cold_water_temp=self.cold_water_temp,
            max_flow_rate=self.max_flow_rate,
            max_steps=self.max_steps,
            render_mode="human"
        )
    
    def get_system_context(self):
        """Get current system state as context for the AI."""
        return f"""Current System Configuration:
- Target Temperature: {self.target_temp}°C
- Initial Temperature: {self.initial_temp}°C
- Hot Water Temperature: {self.hot_water_temp}°C
- Cold Water Temperature: {self.cold_water_temp}°C
- Max Flow Rate: {self.max_flow_rate}
- Max Steps: {self.max_steps}"""
    
    def extract_parameters_from_message(self, message):
        """Extract temperature and parameter values from user message."""
        # Extract numbers
        numbers = re.findall(r'-?\d+\.?\d*', message)
        
        # Look for parameter keywords
        msg_lower = message.lower()
        params = {}
        
        # Target temperature
        if any(word in msg_lower for word in ['target', 'goal', 'want', 'need', 'heat to', 'cool to', 'reach', 'set to']):
            if numbers:
                params['target'] = float(numbers[0])
        
        # Initial temperature
        if any(phrase in msg_lower for phrase in ['start from', 'starting', 'initial', 'begin', 'beginning']):
            if numbers:
                params['initial'] = float(numbers[0])
        
        # Hot water
        if 'hot' in msg_lower and ('water' in msg_lower or 'temp' in msg_lower):
            if numbers:
                params['hot'] = float(numbers[0])
        
        # Cold water
        if 'cold' in msg_lower and ('water' in msg_lower or 'temp' in msg_lower):
            if numbers:
                params['cold'] = float(numbers[0])
        
        # If just a number and no clear context, assume it's a target
        if not params and numbers and 0 <= float(numbers[0]) <= 100:
            params['target'] = float(numbers[0])
        
        return params
    
    def chat_with_local_ai(self, user_message):
        """Get AI response using local Ollama model."""
        # Add system context to the message
        context = self.get_system_context()
        full_message = f"{context}\n\nUser: {user_message}"
        
        # Add to conversation history
        self.conversation_history.append({"role": "user", "content": full_message})
        
        try:
            # Call Ollama
            response = self.ollama_client.chat(
                model=self.model_name,
                messages=self.conversation_history,
                options={
                    'temperature': 0.7,
                    'num_predict': 200  # Limit response length
                }
            )
            
            ai_response = response['message']['content']
            
            # Add AI response to history (but keep it short)
            self.conversation_history.append({"role": "assistant", "content": ai_response})
            
            # Keep conversation history manageable (last 10 messages)
            if len(self.conversation_history) > 12:  # system + 10 messages
                self.conversation_history = [self.conversation_history[0]] + self.conversation_history[-10:]
            
            return ai_response
        except Exception as e:
            return f"Sorry, I encountered an error: {e}. Let me try a simpler approach."
    
    def handle_ai_response(self, user_message):
        """Process user message and extract actions."""
        # Extract parameters from the conversation
        params = self.extract_parameters_from_message(user_message)
        
        # Apply parameters if found
        actions_taken = []
        if 'target' in params:
            value = params['target']
            if 0 <= value <= 100:
                self.target_temp = value
                self._create_env()
                actions_taken.append(f"Set target to {value}°C")
        
        if 'initial' in params:
            value = params['initial']
            if 0 <= value <= 100:
                self.initial_temp = value
                self._create_env()
                actions_taken.append(f"Set initial temperature to {value}°C")
        
        if 'hot' in params:
            value = params['hot']
            if 0 <= value <= 100:
                self.hot_water_temp = value
                self._create_env()
                actions_taken.append(f"Set hot water to {value}°C")
        
        if 'cold' in params:
            value = params['cold']
            if 0 <= value <= 100:
                self.cold_water_temp = value
                self._create_env()
                actions_taken.append(f"Set cold water to {value}°C")
        
        # Check if user wants to run a test
        msg_lower = user_message.lower()
        run_keywords = ['run', 'test', 'try', 'go', 'start', 'execute', 'show', 'demonstrate', 'control', 'let\'s']
        should_run = any(keyword in msg_lower for keyword in run_keywords)
        
        # Extract number of episodes if mentioned
        numbers = re.findall(r'\d+', user_message)
        num_episodes = int(numbers[0]) if numbers and int(numbers[0]) > 1 else 1
        
        return actions_taken, should_run, num_episodes
    
    def run_episodes(self, num_episodes=1):
        """Run temperature control episodes."""
        if num_episodes > 1:
            print(f"\n🚀 Running {num_episodes} episodes...\n")
        else:
            print(f"\n🚀 Starting temperature control...\n")
        
        for episode in range(num_episodes):
            if num_episodes > 1:
                print(f"--- Episode {episode + 1}/{num_episodes} ---\n")
            
            obs, info = self.env.reset()
            done = False
            total_reward = 0
            steps = 0
            temps = [self.env.current_temp]
            
            print(f"Starting: {self.env.current_temp:.1f}°C → Target: {self.target_temp}°C\n")
            
            while not done:
                action, _states = self.model.predict(obs, deterministic=True)
                obs, reward, terminated, truncated, info = self.env.step(action)
                done = terminated or truncated
                total_reward += reward
                steps += 1
                temps.append(self.env.current_temp)
                
                if steps % 15 == 0 or done:
                    error = abs(self.env.current_temp - self.target_temp)
                    status_emoji = "🎯" if error < 0.5 else "📈" if error < 1.0 else "🌡️"
                    print(f"  {status_emoji} Step {steps}: {self.env.current_temp:.1f}°C (error: {error:.1f}°C)")
            
            final_error = abs(self.env.current_temp - self.target_temp)
            success = final_error < 0.5
            
            print(f"\n📊 Results:")
            print(f"   Final: {self.env.current_temp:.1f}°C | Target: {self.target_temp}°C")
            print(f"   Error: {final_error:.1f}°C | Steps: {steps}")
            
            if success:
                print(f"   ✅ Excellent! Very close to target!")
            elif final_error < 1.0:
                print(f"   👍 Good! Close to target.")
            else:
                print(f"   🤔 Could be better. The model might need more training for this target.")
            print()
    
    def chat(self):
        """Main chat loop."""
        print("\n" + "="*70)
        if self.use_ai:
            print(f"🤖 Local AI-Powered Temperature Control Chat ({self.model_name})")
        else:
            print("🤖 Temperature Control Chat (Rule-Based)")
        print("="*70)
        print("\nHi! I'm your AI temperature control assistant. 😊")
        print("I can help you control water temperature by mixing hot and cold water.")
        if self.use_ai:
            print(f"I'm powered by a local AI model ({self.model_name}), so everything runs on your machine!")
        print("\nYou can:")
        print("  • Set target temperatures")
        print("  • Adjust starting conditions")
        print("  • Run temperature control tests")
        print("  • Ask questions about the system")
        print("\nSay 'goodbye' to exit.\n")
        print("="*70 + "\n")
        
        while True:
            try:
                user_input = input("You: ").strip()
                if not user_input:
                    continue
                
                # Check for exit
                if any(word in user_input.lower() for word in ['bye', 'goodbye', 'exit', 'quit']):
                    print("\n🤖 👋 Goodbye! It was great chatting with you!")
                    break
                
                # Get AI response if available
                if self.use_ai:
                    ai_response = self.chat_with_local_ai(user_input)
                    actions, should_run, num_episodes = self.handle_ai_response(user_input)
                    
                    print(f"🤖 {ai_response}\n")
                    
                    if actions:
                        print("   (Applied: " + ", ".join(actions) + ")\n")
                    
                    if should_run:
                        self.run_episodes(num_episodes)
                        print("🤖 Anything else you'd like to try?\n")
                else:
                    # Fallback to simple rule-based
                    params = self.extract_parameters_from_message(user_input)
                    msg_lower = user_input.lower()
                    
                    if params:
                        if 'target' in params:
                            self.target_temp = params['target']
                            self._create_env()
                            print(f"🤖 Got it! Target set to {params['target']}°C\n")
                        if 'initial' in params:
                            self.initial_temp = params['initial']
                            self._create_env()
                            print(f"🤖 Starting temperature set to {params['initial']}°C\n")
                    
                    if any(word in msg_lower for word in ['run', 'test', 'try', 'go', 'show']):
                        numbers = re.findall(r'\d+', user_input)
                        num_episodes = int(numbers[0]) if numbers and int(numbers[0]) > 1 else 1
                        self.run_episodes(num_episodes)
                        print("🤖 Anything else?\n")
                    elif any(word in msg_lower for word in ['status', 'current', 'what']):
                        print(f"🤖 {self.get_system_context()}\n")
                    else:
                        print("🤖 I can help you set temperatures or run tests. What would you like to do?\n")
                    
            except KeyboardInterrupt:
                print("\n\n🤖 👋 Goodbye! Thanks for chatting!")
                break
            except EOFError:
                print("\n\n🤖 👋 Goodbye! Thanks for chatting!")
                break


def main():
    """Main entry point."""
    model_path = "models/best/best_model"
    llm_model = "llama3.2"  # Default model, can be changed
    
    # Parse arguments
    args = sys.argv[1:]
    if args:
        if args[0] == '--model' and len(args) > 1:
            llm_model = args[1]
        elif args[0] == '--list-models':
            try:
                import ollama
                models = ollama.list()
                print("Available Ollama models:")
                for model in models['models']:
                    print(f"  - {model['name']}")
                return
            except:
                print("Ollama not available. Install with: pip install ollama")
                return
        else:
            model_path = args[0]
    
    chat = LocalAIChat(model_path, model_name=llm_model)
    chat.chat()


if __name__ == "__main__":
    main()

