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
  
  

  
