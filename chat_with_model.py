"""
Natural language chat interface for the trained temperature control model.
Have a conversation with the AI agent - just talk naturally!
"""
import sys
import re
from stable_baselines3 import PPO
from temperature_env import TemperatureControlEnv


class ModelChat:
    def __init__(self, model_path="models/best/best_model"):
        """Initialize the chat interface with a trained model."""
        print("🤖 Loading AI temperature control agent...")
        try:
            self.model = PPO.load(model_path)
            print("✅ Model loaded successfully!\n")
        except Exception as e:
            print(f"❌ Error loading model: {e}")
            sys.exit(1)
        
        # Default parameters
        self.target_temp = 37.0
        self.initial_temp = 20.0
        self.hot_water_temp = 60.0
        self.cold_water_temp = 10.0
        self.max_flow_rate = 1.0
        self.max_steps = 200
        
        self.env = None
        self._create_env()
        
    def _create_env(self):
        """Create or recreate the environment with current parameters."""
        self.env = TemperatureControlEnv(
            target_temp=self.target_temp,
            initial_temp=self.initial_temp,
            hot_water_temp=self.hot_water_temp,
            cold_water_temp=self.cold_water_temp,
            max_flow_rate=self.max_flow_rate,
            max_steps=self.max_steps,
            render_mode="human"
        )
    
    def extract_number(self, text):
        """Extract a number from text."""
        # Look for numbers (including decimals)
        numbers = re.findall(r'-?\d+\.?\d*', text)
        if numbers:
            try:
                return float(numbers[0])
            except ValueError:
                return None
        return None
    
    def understand_intent(self, message):
        """Understand user intent from natural language."""
        msg_lower = message.lower().strip()
        
        # Exit intents
        if any(word in msg_lower for word in ['bye', 'goodbye', 'exit', 'quit', 'leave', 'stop']):
            return {'intent': 'exit'}
        
        # Status/Info intents
        if any(phrase in msg_lower for phrase in ['status', 'current', 'what is', 'show me', 'tell me', 'how is']):
            if 'target' in msg_lower or 'temperature' in msg_lower:
                return {'intent': 'status'}
            return {'intent': 'status'}
        
        # Help intents
        if any(word in msg_lower for word in ['help', 'what can', 'how do', 'commands', 'options']):
            return {'intent': 'help'}
        
        # Target temperature intents
        target_keywords = ['target', 'goal', 'want', 'need', 'set to', 'heat to', 'cool to', 
                          'reach', 'achieve', 'temperature of', 'temp of', 'degrees']
        if any(keyword in msg_lower for keyword in target_keywords):
            number = self.extract_number(message)
            if number is not None:
                return {'intent': 'set_target', 'value': number}
            else:
                return {'intent': 'set_target', 'value': None, 'error': 'no_number'}
        
        # Initial temperature intents
        if any(phrase in msg_lower for phrase in ['start from', 'starting at', 'initial', 'begin at', 'beginning']):
            number = self.extract_number(message)
            if number is not None:
                return {'intent': 'set_initial', 'value': number}
            else:
                return {'intent': 'set_initial', 'value': None, 'error': 'no_number'}
        
        # Hot water temperature intents
        if any(phrase in msg_lower for phrase in ['hot water', 'hot temp', 'hotter']):
            number = self.extract_number(message)
            if number is not None:
                return {'intent': 'set_hot', 'value': number}
        
        # Cold water temperature intents
        if any(phrase in msg_lower for phrase in ['cold water', 'cold temp', 'colder']):
            number = self.extract_number(message)
            if number is not None:
                return {'intent': 'set_cold', 'value': number}
        
        # Run/Test intents
        run_keywords = ['run', 'test', 'try', 'go', 'start', 'execute', 'do it', 'let\'s', 
                       'show me', 'demonstrate', 'control', 'operate']
        if any(keyword in msg_lower for keyword in run_keywords):
            # Check for number of episodes
            number = self.extract_number(message)
            num_episodes = int(number) if number is not None and number > 1 else 1
            return {'intent': 'run', 'episodes': num_episodes}
        
        # Default: try to extract a number as target if it seems like a temperature
        number = self.extract_number(message)
        if number is not None and 0 <= number <= 100:
            # Likely a temperature
            return {'intent': 'set_target', 'value': number}
        
        # Unknown intent
        return {'intent': 'unknown'}
    
    def respond(self, intent_data):
        """Generate a conversational response based on intent."""
        intent = intent_data.get('intent')
        
        if intent == 'exit':
            return False, "👋 Goodbye! It was great working with you. Feel free to come back anytime!"
        
        elif intent == 'status':
            response = f"Here's the current setup:\n"
            response += f"🎯 Target temperature: {self.target_temp}°C\n"
            response += f"🌡️  Starting temperature: {self.initial_temp}°C\n"
            response += f"🔥 Hot water: {self.hot_water_temp}°C\n"
            response += f"❄️  Cold water: {self.cold_water_temp}°C\n"
            response += f"💧 Max flow rate: {self.max_flow_rate}\n"
            return True, response
        
        elif intent == 'help':
            response = "I can help you control the temperature! Here's what you can say:\n\n"
            response += "• \"Set target to 40 degrees\" or \"I want 45°C\" - Change target temperature\n"
            response += "• \"Start from 25 degrees\" - Set initial temperature\n"
            response += "• \"Run a test\" or \"Let's try it\" - Run the control system\n"
            response += "• \"What's the status?\" - See current settings\n"
            response += "• \"Goodbye\" - Exit\n\n"
            response += "Just talk naturally - I'll understand what you mean! 😊"
            return True, response
        
        elif intent == 'set_target':
            if intent_data.get('error') == 'no_number':
                return True, "I'd be happy to set the target temperature! What temperature would you like? (Just tell me a number, like '40' or '45 degrees')"
            
            value = intent_data.get('value')
            if value is not None:
                if value < 0 or value > 100:
                    return True, f"Hmm, {value}°C seems a bit extreme. Could you pick something between 0 and 100 degrees?"
                
                self.target_temp = value
                self._create_env()
                return True, f"Perfect! I've set the target temperature to {value}°C. Ready to control it when you are!"
            return True, "I'm not sure what temperature you want. Could you tell me a number?"
        
        elif intent == 'set_initial':
            if intent_data.get('error') == 'no_number':
                return True, "Sure! What temperature should we start from? (Just give me a number)"
            
            value = intent_data.get('value')
            if value is not None:
                if value < 0 or value > 100:
                    return True, f"That's quite extreme! Could you pick a starting temperature between 0 and 100 degrees?"
                
                self.initial_temp = value
                self._create_env()
                return True, f"Got it! We'll start from {value}°C. The system is ready!"
            return True, "I didn't catch the starting temperature. Could you give me a number?"
        
        elif intent == 'set_hot':
            value = intent_data.get('value')
            if value is not None:
                self.hot_water_temp = value
                self._create_env()
                return True, f"Hot water temperature set to {value}°C. That should help heat things up!"
            return True, "What temperature should the hot water be?"
        
        elif intent == 'set_cold':
            value = intent_data.get('value')
            if value is not None:
                self.cold_water_temp = value
                self._create_env()
                return True, f"Cold water temperature set to {value}°C. Ready to cool things down!"
            return True, "What temperature should the cold water be?"
        
        elif intent == 'run':
            num_episodes = intent_data.get('episodes', 1)
            return True, None  # Special case - will run episodes
        
        elif intent == 'unknown':
            return True, "I'm not quite sure what you mean. You can ask me to:\n" \
                        "• Set a target temperature (like 'set to 40 degrees')\n" \
                        "• Run a test (like 'let's try it' or 'go')\n" \
                        "• Check the status (like 'what's the current setup?')\n" \
                        "• Get help (just say 'help')\n\n" \
                        "Try rephrasing, or say 'help' for more options!"
        
        return True, "Hmm, I'm not sure how to handle that. Try saying 'help' for options!"
    
    def run_episodes(self, num_episodes=1):
        """Run one or more episodes with conversational output."""
        if num_episodes > 1:
            print(f"\n🚀 Alright! Let me run {num_episodes} episodes for you.\n")
        else:
            print(f"\n🚀 Got it! Let me control the temperature for you.\n")
        
        for episode in range(num_episodes):
            if num_episodes > 1:
                print(f"--- Episode {episode + 1}/{num_episodes} ---\n")
            
            obs, info = self.env.reset()
            done = False
            total_reward = 0
            steps = 0
            temps = [self.env.current_temp]
            
            print(f"Starting from {self.env.current_temp:.1f}°C, aiming for {self.target_temp}°C...\n")
            
            while not done:
                action, _states = self.model.predict(obs, deterministic=True)
                obs, reward, terminated, truncated, info = self.env.step(action)
                done = terminated or truncated
                total_reward += reward
                steps += 1
                temps.append(self.env.current_temp)
                
                # Show progress every 15 steps or at the end
                if steps % 15 == 0 or done:
                    error = abs(self.env.current_temp - self.target_temp)
                    status_emoji = "🎯" if error < 0.5 else "📈" if error < 1.0 else "🌡️"
                    print(f"  {status_emoji} Step {steps}: {self.env.current_temp:.1f}°C (error: {error:.1f}°C)")
            
            # Final results
            final_error = abs(self.env.current_temp - self.target_temp)
            success = final_error < 0.5
            
            print(f"\n📊 Results:")
            print(f"   Final: {self.env.current_temp:.1f}°C | Target: {self.target_temp}°C")
            print(f"   Error: {final_error:.1f}°C | Steps: {steps}")
            
            if success:
                print(f"   ✅ Excellent! Got very close to the target!")
            elif final_error < 1.0:
                print(f"   👍 Pretty good! Close to target.")
            else:
                print(f"   🤔 Hmm, could be better. The model might need more training for this target.")
            
            print()  # Blank line between episodes
    
    def chat(self):
        """Main conversational chat loop."""
        print("\n" + "="*70)
        print("🤖 AI Temperature Control Agent - Natural Language Chat")
        print("="*70)
        print("\nHi! I'm your AI temperature control assistant. 😊")
        print("I can help you control water temperature by mixing hot and cold water.")
        print("\nJust talk to me naturally! For example:")
        print("  • \"I want to heat it to 40 degrees\"")
        print("  • \"Let's start from 25°C\"")
        print("  • \"Run a test\" or \"Show me how it works\"")
        print("  • \"What's the current status?\"")
        print("\nSay 'help' anytime, or 'goodbye' to exit.\n")
        print("="*70 + "\n")
        
        while True:
            try:
                user_input = input("You: ").strip()
                if not user_input:
                    continue
                
                # Understand intent
                intent_data = self.understand_intent(user_input)
                
                # Handle special case for running episodes
                if intent_data.get('intent') == 'run':
                    num_episodes = intent_data.get('episodes', 1)
                    self.run_episodes(num_episodes)
                    print("🤖 Anything else you'd like to try?")
                    continue
                
                # Get response
                should_continue, response = self.respond(intent_data)
                
                if response:
                    print(f"🤖 {response}\n")
                
                if not should_continue:
                    break
                    
            except KeyboardInterrupt:
                print("\n\n🤖 👋 Goodbye! Thanks for chatting!")
                break
            except EOFError:
                print("\n\n🤖 👋 Goodbye! Thanks for chatting!")
                break


def main():
    """Main entry point."""
    model_path = "models/best/best_model"
    
    if len(sys.argv) > 1:
        model_path = sys.argv[1]
    
    chat = ModelChat(model_path)
    chat.chat()


if __name__ == "__main__":
    main()
