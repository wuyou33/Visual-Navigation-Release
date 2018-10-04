from systems.dynamics import Dynamics
from trajectory.trajectory import Trajectory, State
from utils.angle_utils import angle_normalize, rotate_pos_nk2
import tensorflow as tf


class Dubins_v2(Dynamics):
    """ A discrete time dubins car with dynamics
        x(t+1) = x(t) + s1(v_tilde(t)) cos(theta_t)*delta_t
        y(t+1) = y(t) + s1(v_tilde(t)) sin(theta_t)*delta_t
        theta(t+1) = theta_t + s2(w_tilde(t))*delta_t
        Here s1 and s2 represent saturation functions on linear and angular
        velocity respectively. """

    def __init__(self, dt, v_bounds=[0.0, .6], w_bounds=[-1.1, 1.1]):
        super().__init__(dt, x_dim=3, u_dim=2)
        self.v_bounds = v_bounds
        self.w_bounds = w_bounds
        self._angle_dims = 2

    def simulate(self, x_nk3, u_nk2, t=None):
        with tf.name_scope('simulate'):
            v_nk = self.s1(u_nk2[:, :, 0])
            delta_x_nk3 = tf.stack([v_nk*tf.cos(x_nk3[:, :, 2]),
                                    v_nk*tf.sin(x_nk3[:, :, 2]),
                                    self.s2(u_nk2[:, :, 1])], axis=2)
            return x_nk3 + self._dt*delta_x_nk3

    def jac_x(self, trajectory):
        x_nk3, u_nk2 = self.parse_trajectory(trajectory)
        with tf.name_scope('jac_x'):
            vtilde_nk, t_nk = u_nk2[:, :, 0], x_nk3[:, :, 2]
            v_nk = self.s1(vtilde_nk)
            ones_nk = tf.ones(shape=v_nk.shape, dtype=tf.float32)
            zeros_nk = tf.zeros(shape=v_nk.shape, dtype=tf.float32)
            a13_nk = -v_nk*tf.sin(t_nk)*self._dt
            a23_nk = v_nk*tf.cos(t_nk)*self._dt

            # Columns
            a1_nk3 = tf.stack([ones_nk, zeros_nk, zeros_nk], axis=2)
            a2_nk3 = tf.stack([zeros_nk, ones_nk, zeros_nk], axis=2)
            a3_nk3 = tf.stack([a13_nk, a23_nk, ones_nk], axis=2)

            A_nk33 = tf.stack([a1_nk3, a2_nk3, a3_nk3], axis=3)
            return A_nk33

    def jac_u(self, trajectory):
        x_nk3, u_nk2 = self.parse_trajectory(trajectory)
        with tf.name_scope('jac_u'):
            t_nk = x_nk3[:, :, 2]
            vtilde_nk = u_nk2[:, :, 0]
            wtilde_nk = u_nk2[:, :, 1]
            vtilde_prime_nk = self.s1_prime(vtilde_nk)
            wtilde_prime_nk = self.s2_prime(wtilde_nk)

            zeros_nk = tf.zeros(shape=t_nk.shape, dtype=tf.float32)
            b11_nk = vtilde_prime_nk*tf.cos(t_nk)*self._dt
            b21_nk = vtilde_prime_nk*tf.sin(t_nk)*self._dt
            b32_nk = wtilde_prime_nk*self._dt

            # Columns
            b1_nk2 = tf.stack([b11_nk, b21_nk, zeros_nk], axis=2)
            b2_nk2 = tf.stack([zeros_nk, zeros_nk, b32_nk], axis=2)

            B_nk23 = tf.stack([b1_nk2, b2_nk2], axis=3)
            return B_nk23

    def s1(self, vtilde_nk):
        """ Saturation function for linear velocity"""
        v_nk = tf.clip_by_value(vtilde_nk, self.v_bounds[0], self.v_bounds[1])
        return v_nk

    def s2(self, wtilde_nk):
        """ Saturation function for angular velocity"""
        w_nk = tf.clip_by_value(wtilde_nk, self.w_bounds[0], self.w_bounds[1])
        return w_nk

    def s1_prime(self, vtilde_nk):
        """ ds1/dvtilde_nk evaluated at vtilde_nk """
        less_than_idx = (vtilde_nk < self.v_bounds[0])
        greater_than_idx = (vtilde_nk > self.v_bounds[1])
        zero_idxs = tf.logical_or(less_than_idx, greater_than_idx)
        res = tf.cast(tf.logical_not(zero_idxs), vtilde_nk.dtype)
        return res

    def s2_prime(self, wtilde_nk):
        """ ds2/dwtilde_nk evaluated at wtilde_nk """
        less_than_idx = (wtilde_nk < self.w_bounds[0])
        greater_than_idx = (wtilde_nk > self.w_bounds[1])
        zero_idxs = tf.logical_or(less_than_idx, greater_than_idx)
        res = tf.cast(tf.logical_not(zero_idxs), wtilde_nk.dtype)
        return res

    def parse_trajectory(self, trajectory):
        """ A utility function for parsing a trajectory object.
        Returns x_nkd, u_nkf which are states and actions for the
        system """
        return trajectory.position_and_heading_nk3(), trajectory.speed_and_angular_speed()

    def assemble_trajectory(self, x_nk3, u_nk2, pad_mode=None):
        """ A utility function for assembling a trajectory object
        from x_nkd, u_nkf, a list of states and actions for the system.
        Here d=3=state dimension and u=2=action dimension. """
        n = x_nk3.shape[0].value
        k = x_nk3.shape[1].value
        if pad_mode == 'zero':  # the last action is 0
            if u_nk2.shape[1]+1 == k:
                u_nk2 = tf.concat([u_nk2, tf.zeros((n, 1, self._u_dim))],
                                  axis=1)
            else:
                assert(u_nk2.shape[1] == k)
        # the last action is the same as the second to last action
        elif pad_mode == 'repeat':
            if u_nk2.shape[1]+1 == k:
                u_end_n12 = tf.zeros((n, 1, self._u_dim)) + u_nk2[:, -1:]
                u_nk2 = tf.concat([u_nk2, u_end_n12], axis=1)
            else:
                assert(u_nk2.shape[1] == k)
        else:
            assert(pad_mode is None)
        position_nk2, heading_nk1 = x_nk3[:, :, :2], x_nk3[:, :, 2:3]
        speed_nk1, angular_speed_nk1 = u_nk2[:, :, 0:1], u_nk2[:, :, 1:2]
        speed_nk1 = self.s1(speed_nk1)
        angular_speed_nk1 = self.s2(angular_speed_nk1)
        return Trajectory(dt=self._dt, n=n, k=k, position_nk2=position_nk2,
                          heading_nk1=heading_nk1, speed_nk1=speed_nk1,
                          angular_speed_nk1=angular_speed_nk1, variable=False)

    @staticmethod
    def init_egocentric_robot_state(dt, n, v=0.0, w=0.0, dtype=tf.float32):
        """ A utility function initializing the robot at
        [x, y, theta] = [0, 0, 0] applying control
        [v, omega] = [v, w] """
        k = 1
        position_nk2 = tf.zeros((n, k, 2), dtype=dtype)
        heading_nk1 = tf.zeros((n, k, 1), dtype=dtype)
        speed_nk1 = v*tf.ones((n, k, 1), dtype=dtype)
        angular_speed_nk1 = w*tf.ones((n, k, 1), dtype=dtype)
        return State(dt=dt, n=n, k=k, position_nk2=position_nk2,
                     heading_nk1=heading_nk1, speed_nk1=speed_nk1,
                     angular_speed_nk1=angular_speed_nk1, variable=False)

    @staticmethod
    def to_egocentric_coordinates(ref_state, traj):
        """ Converts traj to an egocentric reference frame assuming
        ref_state is the origin."""
        ref_position_1k2 = ref_state.position_nk2()
        ref_heading_1k1 = ref_state.heading_nk1()
        position_nk2 = traj.position_nk2()
        heading_nk1 = traj.heading_nk1()

        position_nk2 = position_nk2 - ref_position_1k2
        position_nk2 = rotate_pos_nk2(position_nk2, -ref_heading_1k1)
        heading_nk1 = angle_normalize(heading_nk1 - ref_heading_1k1)

        if traj.k == 1:
            cls = State
        else:
            cls = Trajectory
        return cls(dt=traj.dt, n=traj.n, k=traj.k,
                   position_nk2=position_nk2,
                   speed_nk1=traj.speed_nk1(),
                   acceleration_nk1=traj.acceleration_nk1(),
                   heading_nk1=heading_nk1,
                   angular_speed_nk1=traj.angular_speed_nk1(),
                   angular_acceleration_nk1=traj.angular_acceleration_nk1(),
                   direct_init=True)

    @staticmethod
    def to_world_coordinates(ref_state, traj):
        """ Converts traj to the world coordinate frame assuming
        ref_state is the origin of the egocentric coordinate frame
        in the world coordinate frame."""
        ref_position_1k2 = ref_state.position_nk2()
        ref_heading_1k1 = ref_state.heading_nk1()
        position_nk2 = traj.position_nk2()
        heading_nk1 = traj.heading_nk1()

        position_nk2 = rotate_pos_nk2(position_nk2, ref_heading_1k1)
        position_nk2 = position_nk2 + ref_position_1k2
        heading_nk1 = angle_normalize(heading_nk1 + ref_heading_1k1)

        if traj.k == 1:
            cls = State
        else:
            cls = Trajectory
        return cls(dt=traj.dt, n=traj.n, k=traj.k,
                   position_nk2=position_nk2,
                   speed_nk1=traj.speed_nk1(),
                   acceleration_nk1=traj.acceleration_nk1(),
                   heading_nk1=heading_nk1,
                   angular_speed_nk1=traj.angular_speed_nk1(),
                   angular_acceleration_nk1=traj.angular_acceleration_nk1(),
                   direct_init=True)
