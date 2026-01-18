"""
AI-powered chat interface for the trained temperature control model.
Uses OpenAI GPT for natural conversation, while controlling the temperature system.
"""
import sys
import os
import re
import json
from stable_baselines3 import PPO
from temperature_env import TemperatureControlEnv

# Try to import OpenAI, but make it optional
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("⚠️  OpenAI not installed. Install with: pip install openai")
    print("   Falling back to rule-based chat...")


class AIChat:
    def __init__(self, model_path="models/best/best_model", use_ai=True):
        """Initialize the AI chat interface."""
        print("🤖 Loading AI temperature control agent...")
        try:
            self.model = PPO.load(model_path)
            print("✅ Control model loaded successfully!")
        except Exception as e:
            print(f"❌ Error loading model: {e}")
            sys.exit(1)
        
        # Check if we can use AI chat
        self.use_ai = use_ai and OPENAI_AVAILABLE
        if self.use_ai:
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                print("⚠️  OPENAI_API_KEY not found in environment.")
                print("   Set it with: export OPENAI_API_KEY='your-key-here'")
                print("   Falling back to rule-based chat...")
                self.use_ai = False
            else:
                self.client = OpenAI(api_key=api_key)
                print("✅ AI chat enabled (using OpenAI GPT)")
        else:
            print("ℹ️  Using rule-based chat (install openai and set API key for AI chat)")
        
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
        self.conversation_history = [
            {
                "role": "system",
                "content": """You are a helpful AI assistant that controls a water temperature system. 
You can mix hot and cold water to reach target temperatures. 

Your capabilities:
- Set target temperature (user says things like "I want 40 degrees" or "heat to 45°C")
- Set initial/starting temperature (user says "start from 25" or "begin at 30°C")
- Run temperature control tests (user says "run a test", "try it", "show me", "go")
- Check current status (user says "what's the status", "current settings")
- Adjust hot/cold water temperatures if needed

When the user wants to set parameters, extract the values and confirm. When they want to run a test, 
acknowledge and prepare to run it. Be friendly, conversational, and helpful.

Current system state will be provided in your context. Always confirm changes before applying them."""
            }
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
        if any(word in msg_lower for word in ['target', 'goal', 'want', 'need', 'heat to', 'cool to', 'reach']):
            if numbers:
                params['target'] = float(numbers[0])
        
        # Initial temperature
        if any(phrase in msg_lower for phrase in ['start from', 'starting', 'initial', 'begin']):
            if numbers:
                params['initial'] = float(numbers[0])
        
        # Hot water
        if 'hot' in msg_lower and 'water' in msg_lower:
            if numbers:
                params['hot'] = float(numbers[0])
        
        # Cold water
        if 'cold' in msg_lower and 'water' in msg_lower:
            if numbers:
                params['cold'] = float(numbers[0])
        
        # If just a number and no clear context, assume it's a target
        if not params and numbers and 0 <= float(numbers[0]) <= 100:
            params['target'] = float(numbers[0])
        
        return params
    
    def chat_with_ai(self, user_message):
        """Get AI response using OpenAI."""
        # Add system context
        context_message = self.get_system_context()
        
        # Add user message with context
        full_message = f"{context_message}\n\nUser: {user_message}"
        self.conversation_history.append({"role": "user", "content": full_message})
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",  # Using mini for cost efficiency, can change to gpt-4
                messages=self.conversation_history,
                temperature=0.7,
                max_tokens=200
            )
            
            ai_response = response.choices[0].message.content
            self.conversation_history.append({"role": "assistant", "content": ai_response})
            
            return ai_response
        except Exception as e:
            return f"Sorry, I encountered an error: {e}. Let me try a simpler approach."
    
    def handle_ai_response(self, user_message, ai_response):
        """Process AI response and extract actions."""
        # Extract parameters from the conversation
        params = self.extract_parameters_from_message(user_message)
        
        # Apply parameters if found
        actions_taken = []
        if 'target' in params:
            self.target_temp = params['target']
            self._create_env()
            actions_taken.append(f"Set target to {params['target']}°C")
        
        if 'initial' in params:
            self.initial_temp = params['initial']
            self._create_env()
            actions_taken.append(f"Set initial temperature to {params['initial']}°C")
        
        if 'hot' in params:
            self.hot_water_temp = params['hot']
            self._create_env()
            actions_taken.append(f"Set hot water to {params['hot']}°C")
        
        if 'cold' in params:
            self.cold_water_temp = params['cold']
            self._create_env()
            actions_taken.append(f"Set cold water to {params['cold']}°C")
        
        # Check if user wants to run a test
        msg_lower = user_message.lower()
        run_keywords = ['run', 'test', 'try', 'go', 'start', 'execute', 'show', 'demonstrate', 'control']
        should_run = any(keyword in msg_lower for keyword in run_keywords)
        
        return ai_response, actions_taken, should_run
    
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
            print("🤖 AI-Powered Temperature Control Chat (GPT-4)")
        else:
            print("🤖 Temperature Control Chat (Rule-Based)")
        print("="*70)
        print("\nHi! I'm your AI temperature control assistant. 😊")
        print("I can help you control water temperature by mixing hot and cold water.")
        if self.use_ai:
            print("I'm powered by AI, so feel free to chat naturally with me!")
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
                    ai_response, actions, should_run = self.handle_ai_response(user_input, None)
                    ai_response = self.chat_with_ai(user_input)
                    print(f"🤖 {ai_response}\n")
                    
                    if actions:
                        print("   (Applied: " + ", ".join(actions) + ")\n")
                    
                    if should_run:
                        # Extract number of episodes if mentioned
                        numbers = re.findall(r'\d+', user_input)
                        num_episodes = int(numbers[0]) if numbers and int(numbers[0]) > 1 else 1
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
    use_ai = True
    
    if len(sys.argv) > 1:
        if sys.argv[1] == '--no-ai':
            use_ai = False
        else:
            model_path = sys.argv[1]
    
    chat = AIChat(model_path, use_ai=use_ai)
    chat.chat()


if __name__ == "__main__":
    main()

