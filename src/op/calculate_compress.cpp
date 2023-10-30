#include <torch/extension.h>
#include "calculate_compress.h"

void torch_launch_calculate_compress(
                        const torch::Tensor &f2,
                        const torch::Tensor &coefficient,
                        int64_t sij_num,
                        int64_t layer_node,
                        int64_t coe_num,
                        const torch::Tensor &G
)
{
    auto dtype = f2.dtype();
    assert(coefficient.dtype() == dtype);
    assert(G.dtype() == dtype);
    if (dtype == torch::kFloat32)
    {
        launch_calculate_compress<float>(
            (const float *) f2.data_ptr(),
            (const float *) coefficient.data_ptr(),
            sij_num, layer_node, coe_num,
            (float *) G.data_ptr()
        );
    } else if (dtype == torch::kFloat64)
    {
        launch_calculate_compress<double>(
            (const double *) f2.data_ptr(),
            (const double *) coefficient.data_ptr(),
            sij_num, layer_node, coe_num,
            (double *) G.data_ptr()
        );
    }
    else
        printf("data type error!");
}
