from systems.dynamics import Dynamics
from trajectory.trajectory import Trajectory
import tensorflow as tf

class Dubins_v1(Dynamics):
    """ A discrete time dubins car with dynamics
        x(t+1) = x(t) + v(t) cos(theta_t)*delta_t
        y(t+1) = y(t) + v(t) sin(theta_t)*delta_t
        theta(t+1) = theta_t + w_t*delta_t
    """
    def __init__(self, dt):
        super().__init__(dt, x_dim=3, u_dim=2)
        self._angle_dims = 2

    def simulate(self, x_nk3, u_nk2):
        # Note(Somil):
        #  1. Match the signature of the function between the parent and the child class.
        #  2. Style guide.
        #  3. What is tp1? If it is (t+1) then can we call it next or something? tp1 concatenated with nk3 is a bit
        #  confusing.
        #  4. We should use the vector computation for the tensors below. Slicing each state and stacking them back can
        #  very quickly become an overhead and should be avoided.
        with tf.name_scope('simulate'):
            x_nk, y_nk, t_nk = x_nk3[:,:,0], x_nk3[:,:,1], x_nk3[:,:,2]
            v_nk, w_nk = u_nk2[:,:,0], u_nk2[:,:,1]

            x_tp1_nk = x_nk + v_nk * tf.cos(t_nk) * self._dt
            y_tp1_nk = y_nk + v_nk * tf.sin(t_nk) * self._dt
            t_tp1_nk = t_nk + w_nk * self._dt
            x_tp1_nk3 = tf.stack([x_tp1_nk, y_tp1_nk, t_tp1_nk], axis=2)
            return x_tp1_nk3
    
    def jac_x(self, trajectory):
        # Note(Somil): Again avoid stacking and use tensor level computations if possible.
        x_nk3, u_nk2 = self.parse_trajectory(trajectory)
        with tf.name_scope('jac_x'):
            v_nk, t_nk = u_nk2[:,:,0], x_nk3[:,:,2]
            ones_nk = tf.ones(shape=v_nk.shape, dtype=tf.float32)
            zeros_nk = tf.zeros(shape=v_nk.shape, dtype=tf.float32)
            a13_nk = -v_nk*tf.sin(t_nk)*self._dt
            a23_nk = v_nk*tf.cos(t_nk)*self._dt

            #Columns
            a1_nk3 = tf.stack([ones_nk, zeros_nk, zeros_nk], axis=2)
            a2_nk3 = tf.stack([zeros_nk, ones_nk, zeros_nk], axis=2)
            a3_nk3 = tf.stack([a13_nk, a23_nk, ones_nk], axis=2)
            
            A_nk33 = tf.stack([a1_nk3, a2_nk3, a3_nk3], axis=3)
            return A_nk33

    def jac_u(self, trajectory):
        x_nk3, u_nk2 = self.parse_trajectory(trajectory)
        with tf.name_scope('jac_u'):
            t_nk = x_nk3[:,:,2]

            zeros_nk = tf.zeros(shape=t_nk.shape, dtype=tf.float32)
            ones_nk = tf.ones(shape=t_nk.shape, dtype=tf.float32)
            b11_nk = tf.cos(t_nk)*self._dt
            b21_nk = tf.sin(t_nk)*self._dt
           
            #Columns 
            b1_nk2 = tf.stack([b11_nk, b21_nk, zeros_nk], axis=2)
            b2_nk2 = tf.stack([zeros_nk, zeros_nk, ones_nk*self._dt], axis=2)
            
            B_nk23 = tf.stack([b1_nk2, b2_nk2], axis=3)
            return B_nk23

    def parse_trajectory(self, trajectory):
        # Note(Somil): Could you add the dimension information to speed_and_angular_speed function of trajectory?
        return trajectory.position_and_heading_nk3(), trajectory.speed_and_angular_speed()

    def assemble_trajectory(self, x_nk3, u_nk2, zero_pad_u=False):
        n = x_nk3.shape[0].value
        k = x_nk3.shape[1].value
        if zero_pad_u: # the last action is 0
            # Note(Somil): Haven't we just computed n, k above? Is the computation here any different? Also, we should
            # be able to do n, k, _ = x_nk3.shape in eager mode.
            n = x_nk3.shape[0].value
            k = x_nk3.shape[1].value
            if u_nk2.shape[1]+1 == k:
                u_nk2 = tf.concat([u_nk2, tf.zeros((n, 1, self._u_dim))], axis=1) #0 control @ last time step
            else:
                assert(u_nk2.shape[1] == k)
        # Note(Somil): Style guide.
        position_nk2, heading_nk1 = x_nk3[:,:,:2], x_nk3[:,:,2:3]
        speed_nk1, angular_speed_nk1 = u_nk2[:,:,0:1], u_nk2[:,:,1:2]
        return Trajectory(dt=self._dt, n=n, k=k, position_nk2=position_nk2,
                        heading_nk1=heading_nk1, speed_nk1=speed_nk1,
                        angular_speed_nk1=angular_speed_nk1, variable=False)
