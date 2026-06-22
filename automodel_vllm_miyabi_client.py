import os
from typing import List
from multipl_e.completions import make_main, stop_at_stop_token, partial_arg_parser
from openai import OpenAI

class VLLMClient:
    def __init__(self, name: str, api_base: str):
        """
        Initializes the OpenAI client to connect to the vLLM server.
        
        :param name: The model name/path used by the server. This will be passed in the API request.
        :param api_base: The base URL of the vLLM server (e.g., "http://<master_node_ip>:8000/v1").
        """
        self.client = OpenAI(api_key="NOT_USED", base_url=api_base)
        self.model_name = name

    def completions(
        self, prompts: List[str], max_tokens: int, temperature: float, top_p: float, stop: List[str]
    ):
        """
        Generates completions for a list of prompts by calling the vLLM API.
        """
        prompts = [prompt.strip() for prompt in prompts]

        response = self.client.completions.create(
            model=self.model_name,
            prompt=prompts,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=stop,
        )
        
        results = []
        for choice in response.choices:
            text = choice.text
            text = stop_at_stop_token(text, stop)
            cumulative_logprob = None 
            token_ids = []
            results.append((text, cumulative_logprob, token_ids))
        
        return results


def automodel_partial_arg_parser():
    """
    Adds arguments for model name, server address, and other parameters.
    """
    args = partial_arg_parser()
    args.add_argument("--name", type=str, required=True, help="Path to the model on the server.")
    args.add_argument("--api-base", type=str, required=True, help="Base URL for the vLLM API server (e.g. http://<ip>:8000/v1)")
    args.add_argument("--name-override", type=str, help="Override for the output directory name.")
    args.add_argument("--num-gpus", type=int, default=1, help="Not used by the client, for compatibility.")
    return args


def do_name_override(args):
    """
    Applies the --name-override flag, or uses the model name.
    """
    if args.name_override:
        name = args.name_override
    else:
        name = args.name.replace("/", "_").replace("-", "_")
    return name


def main():
    parser = automodel_partial_arg_parser()
    args = parser.parse_args()
    model_client = VLLMClient(name=args.name, api_base=args.api_base)
    name = do_name_override(args)
    
    make_main(args, name, model_client.completions)


if __name__ == "__main__":
    main()