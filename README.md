# ComfyUI-WBLESS
ComfyUI custom node package. This custom node features multiple practical functions, including global variables, flow control, obtaining image or mask dimensions, and Dominant Axis Scale.
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
- V2.2.0 Update the Area Based Scale Node.
- V2.1.2 Import the cozy_comfyui module and fix the issue where users cannot import the cozy_comfyui module.
- V2.1.1 Fixed the Get Mask Size node returning wrong dimensions in certain scenarios.
- V2.1.0 Updated the Dominant Axis Scale, Get Image Size, and Get Mask Size nodes.
- V2.0.0 is released. This is the first public version. Version 1.0 is an internal test version and will not be made public.
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
### Dominant Axis Scale
> Smart scale input group A relative to input group B, using its longest side as the scaling axis.
> <details>
> <summary>See More Information</summary>
>
> - Height a, Width a — these are the input dimensions you need to scale.
> - Height b, Width b — these reference dimensions serve as the scaling baseline, which you can conceptualize as canvas dimensions.
> - ratio — Input your scaling factor here.
> - The output Width, Height, and scale_ratio govern different output formats.
><img width="3303" height="1224" alt="workflow (1)" src="https://github.com/user-attachments/assets/8c286089-8346-47e1-94a4-f757997d0e9a" />
>
> </details>
### Area Based Scale
> Smart scale the area of input group A with reference to the area of input group B.
> <details>
> <summary>See More Information</summary>
>
> - Height a, Width a — these are the input dimensions you need to scale.
> - Height b, Width b — these reference dimensions serve as the scaling baseline, which you can conceptualize as canvas dimensions.
> - ratio — Input your scaling factor here.
> - The output Width, Height, and scale_ratio govern different output formats.
> - cap_threshold — the upper scaling limit threshold, beyond which the object will not scale any.
> - enable_cap — threshold activation switch.
><img width="3467" height="1237" alt="Area_Based_Scale_demo" src="https://github.com/user-attachments/assets/8b257d09-aea3-4f03-bd5c-d148cd8832c3" />
>
> </details>
### Get Image Size
> Get Image Dimensions.
> <details>
> <summary>See More Information</summary>
>
><img width="509" height="348" alt="image" src="https://github.com/user-attachments/assets/0f2121c4-0641-4fb2-aaaf-48fac71d0fbb" />
>
> </details>
### Get Mask Size
> Get Mask Dimensions.
> <details>
> <summary>See More Information</summary>
>
><img width="757" height="527" alt="image" src="https://github.com/user-attachments/assets/935a2181-1113-4217-aa2c-eb11340463bf" />
>
> </details> 
