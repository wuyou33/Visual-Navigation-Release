from trajectory.spline.spline  import Spline
import tensorflow as tf
import tensorflow.contrib.eager as tfe

class Spline3rdOrder(Spline):
    """ A class representing a 3rd order spline for a mobile ground robot (in a 2d cartesian plane).
    The 3rd order spline allows for constraints on the start state, [x0, y0, theta0, v0], 
    and goal state, [xg, yg, thetag, vg]. Angular speeds w0 and wg are not constrainable.
    """
    def __init__(self, dt, n, k, start_n5):
        super().__init__(dt=dt, n=n, k=k)
        self.k = k
        self.start_n5 = tf.constant(start_n5, name='spline_start', dtype=tf.float32)
 
    def fit(self, goal_n5, factors_n2=None):
        self.goal_n5 = goal_n5
        if factors_n2 is None: #compute them heuristically based on dist to goal
            factors = tf.norm(goal_n5[:,:2], axis=1)
            factors_n2 = tf.stack([factors, factors],axis=1)
        start_n5 = self.start_n5
        with tf.name_scope('fit_spline'):
            f1, f2 = factors_n2[:,0:1], factors_n2[:,1:]
            x0, y0, t0 = self.start_n5[:,0:1], self.start_n5[:,1:2], self.start_n5[:,2:3]
            xg, yg, tg = goal_n5[:,0:1], goal_n5[:,1:2], goal_n5[:,2:3]
            v0, vf = start_n5[:,3:4], goal_n5[:,3:4]

            d1 = x0
            c1 = f1*tf.cos(t0)
            a1 = f2*tf.cos(tg)-2*xg+c1+2*d1
            b1 = 3*xg-f2*tf.cos(tg)-2*c1-3*d1
            
            d2 = y0
            c2 = f1*tf.sin(t0)
            a2 = f2*tf.sin(tg)-2*yg+c2+2*d2
            b2 = 3*yg-f2*tf.sin(tg)-2*c2-3*d2

            c3 = v0 / f1
            a3 = (vf/f2) + c3 - 2.
            b3 = 1. - c3 - a3

            self.x_coeffs = [a1,b1,c1,d1]
            self.y_coeffs = [a2,b2,c2,d2]
            self.p_coeffs = [a3,b3,c3]

    def eval_spline(self, ts, calculate_speeds=True):
        """ Evaluates the spline on points in ts
        where ts is unnormalized time"""
        ts = ts / tf.reduce_max(ts,axis=1,keep_dims=1)
        return self._eval_spline(ts, calculate_speeds)

    def _eval_spline(self, ts, calculate_speeds=True):
        """ Evaluates the spline on points in ts
        Assumes ts is normalized to be in [0, 1.]
        """
        a1,b1,c1,d1 = self.x_coeffs
        a2,b2,c2,d2 = self.y_coeffs
        a3,b3,c3 = self.p_coeffs

        with tf.name_scope('eval_spline'):
            t2, t3 = ts*ts, ts*ts*ts
            ps = a3*t3+b3*t2+c3*ts
            p2, p3 = ps*ps, ps*ps*ps
            xs = a1*p3+b1*p2+c1*ps+d1
            ys = a2*p3+b2*p2+d2

            ps_dot = 3*a3*t2+2*b3*ts+c3
            xs_dot = 3*a1*p2+2*b1*ps+c1
            ys_dot = 3*a2*p2+2*b2*ps+c2

            ps_ddot = 6*a3*ts+2*b3
            xs_ddot = 6*a1*ps+2*b1
            ys_ddot = 6*a2*ps+2*b2

            self._position_nk2 = tf.stack([xs,ys],axis=2)
            heading_nk = tf.atan2(ys_dot, xs_dot)
            self._heading_nk1 = heading_nk[:,:,None]
           
            if calculate_speeds: ####CHECK FOR NANS if calculating speeds!!!!
                speed_ps_nk = tf.sqrt(xs_dot**2 + ys_dot**2)
                speed_nk = (speed_ps_nk*ps_dot)
                with tf.name_scope('omega'):
                    ps_sq = tf.square(ps_dot)
                    num_l = tf.multiply(ys_ddot, ps_sq) + tf.multiply(ys_dot, ps_ddot)
                    num_l = tf.multiply(num_l, tf.multiply(xs_dot, ps_dot))
                    num_r = tf.multiply(xs_ddot, ps_sq) + tf.multiply(xs_dot, ps_ddot)
                    num_r = tf.multiply(num_r, tf.multiply(ys_dot, ps_dot))
                    angular_speed_nk = (num_l + num_r) / tf.square(speed_nk)
                self._speed_ps_nk1 = speed_ps_nk[:,:,None] 
                self._speed_nk1 = speed_nk[:,:,None]
                self._angular_speed_nk1 = angular_speed_nk[:,:,None]

    def render(self, ax, batch_idx=0, freq=4):
        super().render(ax, batch_idx, freq) 
        target_state = self.goal_n5[batch_idx]
        ax.quiver([target_state[0]], [target_state[1]], [tf.cos(target_state[2])], [tf.sin(target_state[2])], units='width')
        ax.set_title('3rd Order Spline')

