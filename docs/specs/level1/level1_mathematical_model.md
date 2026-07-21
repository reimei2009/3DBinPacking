# Mô hình MILP chính xác Level 1

Tập chỉ số:

$$
I=\{1,\ldots,n\},\quad K=\{1,\ldots,m\},\quad
P=\{(i,j)\in I^2:i<j\},\quad D=\{L,R,F,B,Dn,Up\}.
$$

Biến quyết định:

$$
u_k\in\{0,1\},\quad a_{ik}\in\{0,1\},\quad
x_i,y_i,z_i\ge0,\quad \delta_{ijkd}\in\{0,1\}.
$$

Với:

$$
M_x=\max_k L_k,\quad M_y=\max_k W_k,\quad M_z=\max_k H_k,
\qquad B=1+\sum_k c_k,
$$

hàm mục tiêu là:

$$
\min\;B\sum_{k\in K}u_k+\sum_{k\in K}c_k u_k.
$$

Các nhóm ràng buộc:

$$
\sum_{k\in K}a_{ik}=1\quad\forall i\in I,
\qquad a_{ik}\le u_k\quad\forall i,k.
$$

$$
\begin{aligned}
x_i+\ell_i&\le L_k+M_x(1-a_{ik}),\\
y_i+w_i&\le W_k+M_y(1-a_{ik}),\\
z_i+h_i&\le H_k+M_z(1-a_{ik}).
\end{aligned}
$$

$$
\sum_{i\in I}q_i a_{ik}\le Q_k u_k\quad\forall k\in K.
$$

$$
\delta_{ijkd}\le a_{ik},\quad\delta_{ijkd}\le a_{jk},
\qquad
\sum_{d\in D}\delta_{ijkd}\ge a_{ik}+a_{jk}-1.
$$

Mỗi hướng trong $D$ kích hoạt một bất đẳng thức Big-M. Ví dụ hướng trái:

$$
x_i+\ell_i\le x_j+M_x(1-\delta_{ijkL}).
$$

Năm hướng còn lại được xây dựng đối xứng cho phải, trước, sau, dưới và trên. Implementation canonical nằm tại `src/container_packing/models/level_01/milp_model.py::build_level1_model`; mapping chỉ số biến nằm tại `model_indices.py`.

Với 20 kiện và 5 container: 5 biến sử dụng + 100 biến gán + 60 tọa độ + 5700 biến phân tách = 5865 biến và 18475 ràng buộc.

Các công thức trên áp dụng cho `milp_big_m`. FFD, Best Fit, Hill Climbing và Simulated Annealing không dựng toàn bộ hệ biến/ràng buộc MILP; chúng xây nghiệm ứng viên và gửi nghiệm cuối qua cùng validator Level 1 độc lập. Best Fit không bổ sung biến hoặc ràng buộc Level 1; nó chỉ thay quy tắc chọn trong tập các vị trí đã thỏa biên, payload và non-overlap.
