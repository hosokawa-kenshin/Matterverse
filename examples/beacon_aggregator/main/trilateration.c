/* 既知の3点の座標，距離を利用して未知の点Pを求めるアルゴリズム */
#include <stdio.h>
#include <math.h>

void calc_line_eq(float a[3],float b[3],float ra,float rb,float z,float c[3]){
  float ABx = 2 * a[0] - 2 * b[0];
  float ABy = 2 * a[1] - 2 * b[1];
  float ABr = (powf(rb, 2) - powf(ra, 2))
            + (powf(a[0], 2) + powf(a[1], 2) + powf(a[2], 2))
            - (powf(b[0], 2) + powf(b[1], 2) + powf(b[2], 2))
            - ((2 * a[2] - 2 * b[2]) * z);
  c[0] = ABx;
  c[1] = ABy;
  c[2] = ABr;
}

void calc_x_from_lines(float a[3],float b[3],float *x){
  float ABx = a[0] * b[1];
  float ABr = a[2] * b[1];
  float ACx = a[1] * b[0];
  float ACr = a[1] * b[2];
  *x = (ABr - ACr) / (ABx - ACx);
}

void calc_y_from_x(float a[3],float x,float *y){
  *y = (a[2]- a[0] * x) / a[1];
}

// int main(void){
//   float a[3];
//   float b[3];
//   float c[3];
//   float AB[3];
//   float AC[3];
//   float X;
//   float Y;
//   float Z = 1.0;

//   a[0] = 0.0;
//   a[1] = 0.0;
//   a[2] = 1.0;
//   b[0] = 0.0;
//   b[1] = 1.0;
//   b[2] = 1.0;
//   c[0] = 1.0;
//   c[1] = 1.0;
//   c[2] = 1.0;

//   float ra = sqrt(0.61);
//   float rb = sqrt(0.41);
//   float rc = sqrt(0.41);

//   calc_line_eq(a,b,ra,rb,Z,AB);
//   calc_line_eq(a,c,ra,rc,Z,AC);
//   calc_x_from_lines(AB,AC,&X);
//   calc_y_from_x(AB,X,&Y);

//   printf("X:%f,Y:%f,Z:%f\n",X,Y,Z);
// }