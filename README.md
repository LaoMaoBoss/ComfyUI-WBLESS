# ComfyUI-WBLESS
ComfyUI's custom node package. This custom node has many practical functions, including global variables and process flow control.
# Get Started
### Recommended
- Install via [ComfyUI-Manager](https://github.com/Comfy-Org/ComfyUI-Manager).
### Manual
- Clone this repo into : `custom_nodes`
   ```
   cd ComfyUI/custom_nodes
   git clone https://github.com/LaoMaoBoss/ComfyUI-WBLESS.git
   ```
- Start up ComfyUI.
# NOTICE
- V2.0 is released. This is the first public version. Version 1.0 is an internal test version and will not be made public.
# The Nodes
### Set Global Variable
> The `Set Global Variable` node allows you to store your data in variables.
> <details>
> <summary>See More Information</summary>
>
> - The `Input` and `Output` nodes form a direct pipeline for better integration within workflows.
> - The `variable data` is used for inputting variable values.
> - `Scope` is used to set the order in which variables are obtained. You just need to connect them in sequence one after another.
> - `variable_name` Here you can set the name of your variable.
><img width="800" height="457" alt="image" src="https://github.com/user-attachments/assets/e5cdebc6-febd-4d1f-8535-4d26da658ef1" />
>
> </details> 
### Get Global Variable
> The `Get Global Variable` node can retrieve data stored in variables.
> <details>
> <summary>See More Information</summary>
>
> - The `Input` and `Output` nodes form a direct pipeline for better integration within workflows.
> - `variable data` is used for outputting the variable's value.
> - `Scope` is used to set the order in which variables are obtained. You just need to connect them in sequence one after another.
> - `variable_name` Here you can specify the variable you want to retrieve.
><img width="721" height="409" alt="image" src="https://github.com/user-attachments/assets/c49fc13b-be0c-4a5c-a9c1-c4e0034e3880" />
>
> </details> 
### Inversed Switch
> Used to control the direction of the workflow.
> <details>
> <summary>See More Information</summary>
>
> - Connect the main workflow to the `Input` interface, then connect the `Output` to different branch workflows. By controlling the `path` value of the node, you can determine which branch the workflow will take.
> - This node needs to be used in conjunction with `Switch`.
> - The core logic of this node draws inspiration from [ComfyUI-Impact-Pack](https://github.com/ltdrdata/ComfyUI-Impact-Pack?tab=readme-ov-file). We would like to express our gratitude to the author of `ComfyUI-Impact-Pack` here.
><img width="4507" height="2165" alt="workflow" src="https://github.com/user-attachments/assets/9a0cc5fe-e7fb-46c7-8751-4a11445433a3" />
>
> </details> 
### Switch
> Select and retrieve data from different processes.
> <details>
> <summary>See More Information</summary>
>
> - This node is usually used in conjunction with the `Inversed Switch` node; of course, you can also use it independently.
> - The `Input` interface connects to different branch workflows, while the `Output` interface will output data from the corresponding workflow based on the value of `path`.
><img width="1088" height="471" alt="image" src="https://github.com/user-attachments/assets/3a228452-94fa-4cee-b558-d2ccf2ca4ffa" />
>
> </details> 
